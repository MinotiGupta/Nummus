import uuid
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from .data_generator import generate_batch
from .root_cause import classify
from .context_builder import build_context
from .bandit import select_action, ARMS
from .survival_gate import should_hold
from .knapsack import schedule, compute_ev, ACTION_COSTS
from .executor import execute_action, compute_baseline

def run_batch_cycle(db: Session, n_events=200):
    cycle_id = str(uuid.uuid4())
    events = generate_batch(n_events)
    
    # Pre-populate accounts
    for e in events:
        db.execute(text("""
            INSERT INTO accounts (account_id, first_failure_at) 
            VALUES (:acc_id, :now)
            ON CONFLICT(account_id) DO NOTHING
        """), {"acc_id": e["account_id"], "now": e["timestamp"]})
        
        db.execute(text("""
            INSERT INTO events (
                event_id, account_id, amount, currency, decline_code, timestamp, batch_id
            ) VALUES (
                :eid, :aid, :amt, :curr, :dc, :ts, :bid
            )
        """), {
            "eid": e["event_id"], "aid": e["account_id"], "amt": e["amount"], 
            "curr": "INR", "dc": e["decline_code"], "ts": e["timestamp"], "bid": cycle_id
        })
    
    db.commit()

    candidates_for_scheduling = []
    baseline_recovered = 0.0
    total_at_risk = 0.0
    
    for e in events:
        total_at_risk += e["amount"]
        
        # Phase 2
        root_cause, retryable = classify(e["decline_code"])
        e["root_cause"] = root_cause
        
        db.execute(text("UPDATE events SET root_cause = :rc, retryable = :ret WHERE event_id = :eid"),
                   {"rc": root_cause, "ret": 1 if retryable else 0, "eid": e["event_id"]})
        
        context_key = build_context(e, root_cause)
        e["context_key"] = context_key
        
        # Baseline check
        baseline_recovered += compute_baseline(e, root_cause)
        
        # Phase 4: Survival Gate
        acc = db.execute(text("SELECT * FROM accounts WHERE account_id = :aid"), {"aid": e["account_id"]}).mappings().first()
        hold, hold_reason = should_hold(dict(acc), e, root_cause)
        
        if hold:
            # Gated. Write decision immediately.
            execute_action(e, root_cause, context_key, "hold_no_action", db, cycle_id,
                           ["hold_no_action"], {}, 0.0, True, hold_reason)
            continue
            
        # Phase 3: Bandit
        eligible_arms = list(ARMS)
        if not retryable:
            eligible_arms = [a for a in eligible_arms if not a.startswith("retry")]
            
        if hold_reason and "forced escalation" in hold_reason:
            eligible_arms = ["escalate_human_call"]
            
        chosen_arm, sampled_probs = select_action(context_key, eligible_arms, db)
        
        # Predict EV (using the sampled prob for simplicity in scheduling)
        prob = sampled_probs.get(chosen_arm, 0.0)
        ev = compute_ev(e["amount"], prob, chosen_arm)
        cost = ACTION_COSTS.get(chosen_arm, 0.0)
        
        candidates_for_scheduling.append({
            "event": e, "root_cause": root_cause, "context_key": context_key,
            "arm": chosen_arm, "ev": ev, "cost": cost,
            "is_call": chosen_arm == "escalate_human_call",
            "is_contact": cost > 0,
            "sampled_probs": sampled_probs,
            "eligible_arms": eligible_arms,
            "stop_reason": hold_reason
        })

    # Phase 5: Knapsack
    selected, deferred = schedule(candidates_for_scheduling, budget_contacts=500, budget_calls=50, budget_spend=5000.0)
    
    total_recovered = 0.0
    
    # Phase 6: Execute
    for c in selected:
        outcome, amt = execute_action(c["event"], c["root_cause"], c["context_key"], c["arm"], db, cycle_id,
                                      c["eligible_arms"], c["sampled_probs"], c["ev"], True, c["stop_reason"])
        total_recovered += amt
        
    for c in deferred:
        execute_action(c["event"], c["root_cause"], c["context_key"], "hold_no_action", db, cycle_id,
                       c["eligible_arms"], c["sampled_probs"], c["ev"], False, "deferred: budget-constrained")

    # Finalize batch
    recovery_rate = (total_recovered / total_at_risk) * 100 if total_at_risk > 0 else 0
    efficiency = ((total_recovered - baseline_recovered) / baseline_recovered) * 100 if baseline_recovered > 0 else 0
    
    db.execute(text("""
        INSERT INTO batch_runs (
            cycle_id, run_at, total_events, total_at_risk_amount, 
            total_recovered_amount, baseline_recovered_amount, recovery_rate, efficiency_vs_baseline
        ) VALUES (
            :cid, :now, :te, :tar, :tr, :br, :rr, :eff
        )
    """), {
        "cid": cycle_id, "now": datetime.datetime.utcnow().isoformat(),
        "te": len(events), "tar": total_at_risk, "tr": total_recovered,
        "br": baseline_recovered, "rr": recovery_rate, "eff": efficiency
    })
    db.commit()
    
    return {
        "cycle_id": cycle_id,
        "total_at_risk": total_at_risk,
        "total_recovered": total_recovered,
        "baseline_recovered": baseline_recovered,
        "recovery_rate": recovery_rate,
        "efficiency": efficiency
    }
