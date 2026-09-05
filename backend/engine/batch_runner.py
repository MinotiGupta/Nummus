"""
batch_runner.py — Phase 7: Main Pipeline Orchestrator

Runs one full batch cycle through all 8 stages:
    1. Generate synthetic events (data_generator)
    2. Classify root cause + build context vector (root_cause, context_builder)
    3. Survival gate — hold, force-escalate, or pass (survival_gate)
    4. Bandit action selection per event (bandit.select_action)
    5. Compute EV and assemble scheduler candidates (knapsack.compute_ev)
    6. Budget-constrained selection (knapsack.schedule)
    7. Simulate execution + write audit trail (executor.execute_action)
    8. Write batch_runs summary row

Returns a summary dict that the API layer serialises to JSON.
"""

import uuid
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from .data_generator import generate_batch, simulate_baseline
from .root_cause import classify
from .context_builder import build_context
from .bandit import select_action, get_posterior_means, ARMS
from .survival_gate import should_hold
from .knapsack import schedule, compute_ev
from .executor import execute_action
from .constants import ACTION_COSTS, RETRY_ARMS


def run_batch_cycle(db: Session, n_events: int = 200) -> dict:
    """
    Run one complete batch cycle.

    Args:
        db:       SQLAlchemy session (injected from FastAPI dependency).
        n_events: Number of synthetic events to generate.

    Returns:
        Summary dict with cycle_id, amounts, rates, and efficiency.
    """
    cycle_id = str(uuid.uuid4())

    # ── Stage 1: Generate synthetic events ───────────────────────────────────
    events = generate_batch(n=n_events)

    # ── Stage 1b: Compute baseline BEFORE running the bandit ─────────────────
    # Locked in now so comparison can't be retroactively skewed.
    baseline_result = simulate_baseline(events)
    baseline_recovered  = baseline_result["baseline_recovered"]
    baseline_per_event  = {r["event_id"]: r for r in baseline_result["per_event"]}

    # ── DB: Upsert accounts + insert events ──────────────────────────────────
    now_str = datetime.datetime.utcnow().isoformat()
    for e in events:
        # Upsert account (ignore if already exists — keeps accumulated history)
        db.execute(
            text("""
                INSERT OR IGNORE INTO accounts
                    (account_id, first_failure_at, contact_count, status, self_resolve_score)
                VALUES
                    (:acc_id, :ts, 0, 'active', 0.3)
            """),
            {"acc_id": e["account_id"], "ts": e["timestamp"]},
        )

        db.execute(
            text("""
                INSERT INTO events
                    (event_id, account_id, event_type, amount, currency,
                     decline_code, timestamp, root_cause, retryable, batch_id)
                VALUES
                    (:eid, :aid, :etype, :amt, :curr,
                     :dc, :ts, :rc, :ret, :bid)
            """),
            {
                "eid":   e["event_id"],
                "aid":   e["account_id"],
                "etype": e["event_type"],
                "amt":   e["amount"],
                "curr":  e["currency"],
                "dc":    e["decline_code"],
                "ts":    e["timestamp"],
                "rc":    e["root_cause"],
                "ret":   1 if e["retryable"] else 0,
                "bid":   cycle_id,
            },
        )

    db.commit()

    # ── Stages 2–5: Process each event ───────────────────────────────────────
    total_at_risk = 0.0
    candidates_for_scheduling: list[dict] = []
    gated_count = 0

    for e in events:
        total_at_risk += e["amount"]
        root_cause = e["root_cause"]
        retryable  = e["retryable"]

        # Stage 2: context vector
        context_key = build_context(e, root_cause)
        e["context_key"] = context_key

        # Stage 4: survival gate
        acc = db.execute(
            text("SELECT * FROM accounts WHERE account_id = :aid"),
            {"aid": e["account_id"]},
        ).mappings().first()
        acc_dict = dict(acc)

        hold, hold_reason = should_hold(acc_dict, e, root_cause)

        if hold:
            # Immediately write a "gated" audit record — no scheduling needed
            execute_action(
                event=e, root_cause=root_cause, context_key=context_key,
                arm="hold_no_action", db=db, cycle_id=cycle_id,
                candidate_arms=["hold_no_action"], sampled_probs={},
                predicted_ev=0.0, budget_selected=True,
                stopping_reason=hold_reason,
            )
            gated_count += 1
            continue

        # Stage 3: bandit arm selection
        eligible_arms = [a for a in ARMS if retryable or a not in RETRY_ARMS]

        # Forced escalation bypasses bandit sampling
        if hold_reason and "forced escalation" in hold_reason:
            eligible_arms = ["escalate_human_call"]

        chosen_arm, sampled_probs = select_action(context_key, eligible_arms, db)

        if chosen_arm is None:
            continue  # degenerate case — skip

        # Stage 5: EV using posterior mean (stable ranking)
        posterior_means = get_posterior_means(context_key, db)
        mean_prob = posterior_means.get(chosen_arm, sampled_probs.get(chosen_arm, 0.1))
        ev   = compute_ev(e["amount"], mean_prob, chosen_arm)
        cost = ACTION_COSTS.get(chosen_arm, 0.0)

        candidates_for_scheduling.append({
            "event":         e,
            "root_cause":    root_cause,
            "context_key":   context_key,
            "arm":           chosen_arm,
            "ev":            ev,
            "cost":          cost,
            "is_call":       chosen_arm == "escalate_human_call",
            "is_contact":    cost > 0,
            "sampled_probs": sampled_probs,
            "eligible_arms": eligible_arms,
            "stop_reason":   hold_reason,
        })

    # ── Stage 5b: Budget-constrained selection ───────────────────────────────
    selected, deferred = schedule(candidates_for_scheduling)

    # ── Stage 6: Execute selected + record deferred ──────────────────────────
    total_recovered = 0.0

    for c in selected:
        _, amt = execute_action(
            event=c["event"], root_cause=c["root_cause"], context_key=c["context_key"],
            arm=c["arm"], db=db, cycle_id=cycle_id,
            candidate_arms=c["eligible_arms"], sampled_probs=c["sampled_probs"],
            predicted_ev=c["ev"], budget_selected=True,
            stopping_reason=c["stop_reason"],
        )
        total_recovered += amt

    for c in deferred:
        execute_action(
            event=c["event"], root_cause=c["root_cause"], context_key=c["context_key"],
            arm="hold_no_action", db=db, cycle_id=cycle_id,
            candidate_arms=c["eligible_arms"], sampled_probs=c["sampled_probs"],
            predicted_ev=c["ev"], budget_selected=False,
            stopping_reason="deferred: budget-constrained",
        )

    # ── Stage 8: Write batch_runs summary ────────────────────────────────────
    recovery_rate      = (total_recovered / total_at_risk * 100) if total_at_risk > 0 else 0.0
    baseline_rate      = (baseline_recovered / total_at_risk * 100) if total_at_risk > 0 else 0.0
    efficiency         = recovery_rate - baseline_rate   # absolute pp difference

    db.execute(
        text("""
            INSERT INTO batch_runs (
                cycle_id, run_at, total_events,
                total_at_risk_amount, total_recovered_amount,
                baseline_recovered_amount, recovery_rate,
                efficiency_vs_baseline
            ) VALUES (
                :cid, :now, :te,
                :tar, :tr,
                :br, :rr,
                :eff
            )
        """),
        {
            "cid":  cycle_id,
            "now":  now_str,
            "te":   len(events),
            "tar":  total_at_risk,
            "tr":   total_recovered,
            "br":   baseline_recovered,
            "rr":   recovery_rate,
            "eff":  efficiency,
        },
    )
    db.commit()

    return {
        "cycle_id":           cycle_id,
        "total_events":       len(events),
        "total_at_risk":      round(total_at_risk, 2),
        "total_recovered":    round(total_recovered, 2),
        "baseline_recovered": round(baseline_recovered, 2),
        "recovery_rate":      round(recovery_rate, 2),
        "baseline_rate":      round(baseline_rate, 2),
        "efficiency":         round(efficiency, 2),   # pp improvement over baseline
        "gated_count":        gated_count,
        "selected_count":     len(selected),
        "deferred_count":     len(deferred),
    }
