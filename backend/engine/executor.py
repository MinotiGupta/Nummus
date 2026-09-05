import uuid
import random
import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from .bandit import update_posterior

# Ground-truth outcome probs
GROUND_TRUTH = {
    ("insufficient_funds",  "retry_delayed_24h"):    0.58,
    ("insufficient_funds",  "send_reminder_sms"):    0.45,
    ("insufficient_funds",  "retry_immediate"):      0.22,
    ("expired_card",        "offer_alt_payment_method"): 0.72,
    ("expired_card",        "send_reminder_email"):  0.55,
    ("processor_error",     "retry_immediate"):      0.78,
    ("processor_error",     "retry_delayed_2h"):     0.65,
    ("issuer_decline_soft", "retry_delayed_24h"):    0.48,
    ("bank_risk_hold",      "escalate_human_call"):  0.40,
    ("stolen_lost_card",    "offer_alt_payment_method"): 0.30,
}

def execute_action(event: dict, root_cause: str, context_key: str, arm: str, db: Session, cycle_id: str, 
                   candidate_arms: list, sampled_probs: dict, predicted_ev: float, budget_selected: bool, 
                   stopping_reason: str):
    
    # 1. Determine outcome based on GROUND_TRUTH simulation
    if arm == "hold_no_action" or not budget_selected:
        outcome = False
        amount_recovered = 0.0
    else:
        prob = GROUND_TRUTH.get((root_cause, arm), 0.10)
        outcome = random.random() < prob
        amount_recovered = event["amount"] if outcome else 0.0

    now = datetime.datetime.utcnow().isoformat()
    
    # 2. Update account status
    contact_count_inc = 1 if arm not in ["hold_no_action", "retry_immediate", "retry_delayed_2h", "retry_delayed_24h"] else 0
    new_status = "recovered" if outcome else "active"
    
    db.execute(text("""
        UPDATE accounts 
        SET contact_count = contact_count + :inc,
            last_action_at = :now,
            status = :status
        WHERE account_id = :acc_id
    """), {
        "inc": contact_count_inc, "now": now, "status": new_status, "acc_id": event["account_id"]
    })

    # 3. Write decision audit
    import json
    decision_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO decisions (
            decision_id, event_id, cycle_id, context_key, candidate_arms,
            sampled_probabilities, chosen_arm, predicted_ev, budget_selected,
            stopping_rule_reason, actual_outcome, amount_recovered, created_at
        ) VALUES (
            :d_id, :e_id, :c_id, :ctx, :cand, :probs, :arm, :ev, :budg, :stop, :outc, :amt, :now
        )
    """), {
        "d_id": decision_id, "e_id": event["event_id"], "c_id": cycle_id, "ctx": context_key,
        "cand": json.dumps(candidate_arms), "probs": json.dumps(sampled_probs), "arm": arm,
        "ev": predicted_ev, "budg": 1 if budget_selected else 0, "stop": stopping_reason or "",
        "outc": 1 if outcome else 0, "amt": amount_recovered, "now": now
    })
    
    # 4. Update Bandit Posterior
    if budget_selected and arm != "hold_no_action":
        update_posterior(context_key, arm, outcome, db)
        
    return outcome, amount_recovered

def compute_baseline(event: dict, root_cause: str) -> float:
    # A simple fixed playbook for baseline comparison
    playbook = {
        "insufficient_funds": "retry_delayed_24h",
        "expired_card": "send_reminder_email",
        "stolen_lost_card": "offer_alt_payment_method",
        "processor_error": "retry_immediate",
        "issuer_decline_soft": "retry_delayed_24h",
        "bank_risk_hold": "escalate_human_call"
    }
    
    arm = playbook.get(root_cause, "send_reminder_email")
    prob = GROUND_TRUTH.get((root_cause, arm), 0.10)
    outcome = random.random() < prob
    return event["amount"] if outcome else 0.0
