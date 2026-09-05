"""
executor.py — Phase 6: Simulated Executor + Audit Log Writer

"Executing" an action in the buildathon means:
  1. Drawing a simulated outcome from GROUND_TRUTH probability table.
  2. Updating the account record (contact_count, status, last_action_at).
  3. Writing the full decision audit record to the decisions table.
  4. Feeding the outcome back into the bandit (posterior update).

The Executor class is intentionally thin so a real PSP/messaging client
(Stripe retry, Twilio SMS, etc.) can be swapped in by replacing the
_simulate_outcome method without touching the audit or bandit logic.
"""

import uuid
import json
import random
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from .constants import GROUND_TRUTH, DEFAULT_SUCCESS_PROB
from .bandit import update_posterior


def _simulate_outcome(root_cause: str, arm: str, event_id: str) -> tuple[bool, float]:
    """
    Draw a deterministic-ish outcome from the hidden ground-truth table.

    Uses a fresh random.Random seeded from (event_id + arm) so outcomes are
    reproducible for any given (event, arm) pair but independent across events.
    """
    prob = GROUND_TRUTH.get((root_cause, arm), DEFAULT_SUCCESS_PROB)
    rng  = random.Random(f"{event_id}:{arm}")
    return rng.random() < prob, prob


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

    Returns:
        (outcome: bool, amount_recovered: float)
    """
    now = datetime.datetime.utcnow().isoformat()

    # ── 1. Simulate outcome ──────────────────────────────────────────────────
    if arm == "hold_no_action" or not budget_selected:
        outcome = False
        amount_recovered = 0.0
        true_prob = 0.0
    else:
        outcome, true_prob = _simulate_outcome(root_cause, arm, event["event_id"])
        amount_recovered = event["amount"] if outcome else 0.0

    # ── 2. Update account state ──────────────────────────────────────────────
    # Only outreach actions (not silent retries) count toward contact_count
    is_outreach = arm in {
        "offer_alt_payment_method",
        "send_reminder_email",
        "send_reminder_sms",
        "escalate_human_call",
    }
    contact_inc = 1 if is_outreach and budget_selected else 0
    new_status  = "recovered" if outcome else "active"

    db.execute(
        text("""
            UPDATE accounts
            SET contact_count = contact_count + :inc,
                last_action_at = :now,
                status = :status
            WHERE account_id = :acc_id
        """),
        {
            "inc":     contact_inc,
            "now":     now,
            "status":  new_status,
            "acc_id":  event["account_id"],
        },
    )

    # ── 3. Write decision audit record ───────────────────────────────────────
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
            "probs": json.dumps(sampled_probs),
            "arm":   arm,
            "ev":    predicted_ev,
            "budg":  1 if budget_selected else 0,
            "stop":  stopping_reason or "",
            "outc":  1 if outcome else 0,
            "amt":   amount_recovered,
            "now":   now,
        },
    )

    # ── 4. Update bandit posterior ───────────────────────────────────────────
    if budget_selected and arm not in {"hold_no_action"}:
        update_posterior(context_key, arm, outcome, db)

    db.commit()
    return outcome, amount_recovered
