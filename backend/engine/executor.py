"""
executor.py — Phase 6: Simulated Executor + Audit Log Writer

"Executing" a recovery action in the buildathon means:
  1. Drawing a simulated outcome from the GROUND_TRUTH probability table.
  2. Updating the account's contact_count, status, and last_action_at.
  3. Writing a complete, immutable audit record to the decisions table.
  4. Feeding the outcome back into the bandit (posterior update) — only for
     actions that were actually budget-selected and not hold_no_action.

Deferred events (budget_selected=False) are recorded with outcome=0 and
amount_recovered=0, but their bandit posteriors are NOT updated — the model
only learns from outcomes it actually caused.

Architecture note:
  The Executor interface is intentionally thin.  The only function that
  touches the simulated environment is _simulate_outcome().  To integrate
  with a real PSP (Stripe retry API) or messaging provider (Twilio SMS),
  replace _simulate_outcome() with an async call to the real service.
  Nothing else in this file changes.

Standalone usage:
  python -m engine.executor
"""

import uuid
import json
import random
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from .constants import GROUND_TRUTH, DEFAULT_SUCCESS_PROB
from .bandit import update_posterior


# ─── Simulation environment ───────────────────────────────────────────────────

def _simulate_outcome(root_cause: str, arm: str, event_id: str) -> tuple[bool, float]:
    """
    Draw a reproducible outcome from the hidden ground-truth table.

    Seeded deterministically from (event_id, arm) so the same
    (event, arm) pair always produces the same outcome — this makes
    convergence tests stable and the baseline comparison fair.

    Returns:
        (outcome: bool, ground_truth_prob: float)
    """
    prob = GROUND_TRUTH.get((root_cause, arm), DEFAULT_SUCCESS_PROB)
    rng  = random.Random(f"{event_id}:{arm}")
    return rng.random() < prob, prob


# ─── Core executor ────────────────────────────────────────────────────────────

def execute_action(
    event: dict,
    root_cause: str,
    context_key: str,
    arm: str,
    db: Session,
    cycle_id: str,
    candidate_arms: list[str],
    sampled_probs: dict[str, float],
    predicted_ev: float,
    budget_selected: bool,
    stopping_reason: str | None,
) -> tuple[bool, float]:
    """
    Execute (simulate) one recovery action and write the full audit record.

    Decision logic:
      - If arm == "hold_no_action" OR budget_selected == False:
          outcome = False, amount_recovered = 0 (no action taken)
          bandit posterior is NOT updated (we didn't cause the outcome)
      - Otherwise:
          Simulate outcome from GROUND_TRUTH
          Update account state
          Update bandit posterior

    Args:
        event:           Event dict (must have event_id, account_id, amount).
        root_cause:      Classified root cause string.
        context_key:     Bandit context key.
        arm:             Chosen arm to execute.
        db:              SQLAlchemy session.
        cycle_id:        Current batch run ID.
        candidate_arms:  All arms considered (for audit record).
        sampled_probs:   Thompson samples drawn (for audit record).
        predicted_ev:    EV estimate used for scheduling (for audit record).
        budget_selected: True if the scheduler included this event.
        stopping_reason: Non-None if survival gate held or force-escalated.

    Returns:
        (outcome: bool, amount_recovered: float)
    """
    now = datetime.datetime.utcnow().isoformat()

    # ── 1. Simulate outcome ──────────────────────────────────────────────────
    is_active_action = budget_selected and arm != "hold_no_action"

    if is_active_action:
        outcome, _prob = _simulate_outcome(root_cause, arm, event["event_id"])
        amount_recovered = event["amount"] if outcome else 0.0
    else:
        outcome = False
        amount_recovered = 0.0

    # ── 2. Update account state ──────────────────────────────────────────────
    # Outreach actions (email, SMS, call, alt-payment offer) count toward the
    # compliance contact limit.  Silent retries do NOT increment contact_count.
    OUTREACH_ARMS = {
        "offer_alt_payment_method",
        "send_reminder_email",
        "send_reminder_sms",
        "escalate_human_call",
    }
    contact_inc = 1 if (arm in OUTREACH_ARMS and is_active_action) else 0

    # Status: recovered > active.  Never regress from recovered.
    new_status = "recovered" if outcome else "active"

    db.execute(
        text("""
            UPDATE accounts
            SET contact_count = contact_count + :inc,
                last_action_at = :now,
                status = CASE WHEN status = 'recovered' THEN 'recovered' ELSE :status END
            WHERE account_id = :acc_id
        """),
        {
            "inc":    contact_inc,
            "now":    now,
            "status": new_status,
            "acc_id": event["account_id"],
        },
    )

    # ── 3. Write immutable decision audit record ─────────────────────────────
    db.execute(
        text("""
            INSERT INTO decisions (
                decision_id, event_id, cycle_id, context_key,
                candidate_arms, sampled_probabilities, chosen_arm,
                predicted_ev, budget_selected, stopping_rule_reason,
                actual_outcome, amount_recovered, created_at
            ) VALUES (
                :did, :eid, :cid, :ctx,
                :cand, :probs, :arm,
                :ev, :budg, :stop,
                :outc, :amt, :now
            )
        """),
        {
            "did":   str(uuid.uuid4()),
            "eid":   event["event_id"],
            "cid":   cycle_id,
            "ctx":   context_key,
            "cand":  json.dumps(candidate_arms),
            "probs": json.dumps({k: round(v, 4) for k, v in sampled_probs.items()}),
            "arm":   arm,
            "ev":    round(predicted_ev, 4),
            "budg":  1 if budget_selected else 0,
            "stop":  stopping_reason or "",
            "outc":  1 if outcome else 0,
            "amt":   round(amount_recovered, 2),
            "now":   now,
        },
    )

    # ── 4. Bandit posterior update ───────────────────────────────────────────
    # Only update when we took an action and observed a real outcome.
    # Deferred events and hold_no_action don't produce learning signal.
    if is_active_action:
        update_posterior(context_key, arm, outcome, db)

    db.commit()
    return outcome, amount_recovered


# ─── Audit helpers ────────────────────────────────────────────────────────────

def get_cycle_audit_summary(cycle_id: str, db: Session) -> dict:
    """
    Aggregate decision-level data for a completed batch cycle.
    Used by the API to enrich /batch-runs/{cycle_id} responses.

    Returns counts by outcome, stopping rule, and arm type.
    """
    rows = db.execute(
        text("""
            SELECT
                chosen_arm,
                stopping_rule_reason,
                actual_outcome,
                budget_selected,
                amount_recovered
            FROM decisions
            WHERE cycle_id = :cid
        """),
        {"cid": cycle_id},
    ).mappings().all()

    total = len(rows)
    recovered   = sum(1 for r in rows if r["actual_outcome"] == 1)
    lost        = sum(1 for r in rows if r["actual_outcome"] == 0 and r["budget_selected"] == 1 and r["chosen_arm"] != "hold_no_action")
    held        = sum(1 for r in rows if r["chosen_arm"] == "hold_no_action" and r["budget_selected"] == 1)
    deferred    = sum(1 for r in rows if r["budget_selected"] == 0)
    escalated   = sum(1 for r in rows if r["chosen_arm"] == "escalate_human_call")
    stop_gated  = sum(1 for r in rows if "gated:" in (r["stopping_rule_reason"] or ""))
    stop_forced = sum(1 for r in rows if "forced escalation" in (r["stopping_rule_reason"] or ""))

    arm_counts: dict[str, int] = {}
    for r in rows:
        arm = r["chosen_arm"]
        arm_counts[arm] = arm_counts.get(arm, 0) + 1

    return {
        "total_decisions":     total,
        "recovered":           recovered,
        "lost":                lost,
        "held_by_gate":        held,
        "deferred_by_budget":  deferred,
        "escalated_to_human":  escalated,
        "gated_stop_count":    stop_gated,
        "forced_escalations":  stop_forced,
        "arm_distribution":    arm_counts,
    }


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from .constants import ARMS, GROUND_TRUTH

    print("\n" + "=" * 60)
    print("  Phase 6 — Executor: outcome simulation tests")
    print("=" * 60 + "\n")

    test_cases = [
        # (root_cause, arm, expected_approx_prob)
        ("processor_error",    "retry_immediate",          0.78),
        ("expired_card",       "offer_alt_payment_method", 0.72),
        ("insufficient_funds", "retry_delayed_24h",        0.58),
        ("bank_risk_hold",     "escalate_human_call",      0.40),
        ("stolen_lost_card",   "offer_alt_payment_method", 0.30),
    ]

    print("  Deterministic outcome seeding (same event_id -> same outcome):\n")
    all_pass = True
    for cause, arm, expected_prob in test_cases:
        event_id = f"test-event-{cause[:6]}"

        # Same seed -> same outcome always
        out1, p1 = _simulate_outcome(cause, arm, event_id)
        out2, p2 = _simulate_outcome(cause, arm, event_id)
        deterministic = (out1 == out2 and p1 == p2)
        prob_match    = abs(p1 - expected_prob) < 0.001

        ok = deterministic and prob_match
        if not ok: all_pass = False

        print(f"  {'PASS' if ok else 'FAIL'}  {cause:<25} / {arm:<30}")
        print(f"         prob={p1:.2f} (expected {expected_prob})  "
              f"outcome={out1}  deterministic={deterministic}")

    print(f"\n  {'All tests passed!' if all_pass else 'SOME FAILED'}\n")

    # Show empirical accuracy over 500 trials for one case
    print("  Empirical accuracy over 500 unique event_ids (processor_error/retry_immediate):")
    successes = sum(
        1 for i in range(500)
        if _simulate_outcome("processor_error", "retry_immediate", f"evt-{i}")[0]
    )
    empirical = successes / 500
    print(f"    Successes: {successes}/500  = {empirical:.3f}  (ground truth: 0.78)")
    ok = abs(empirical - 0.78) < 0.05
    print(f"    {'[PASS]' if ok else '[WARN]'}  Within 5pp of ground truth\n")
    print("=" * 60 + "\n")
