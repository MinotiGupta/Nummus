ACTION_COSTS = {
    "retry_immediate":         0.0,
    "retry_delayed_2h":        0.0,
    "retry_delayed_24h":       0.0,
    "offer_alt_payment_method": 2.0,
    "send_reminder_email":     0.5,
    "send_reminder_sms":       0.5,
    "escalate_human_call":     150.0,
    "hold_no_action":          0.0,
}

def compute_ev(amount: float, prob: float, arm: str) -> float:
    cost = ACTION_COSTS.get(arm, 0.0)
    return (prob * amount) - cost

def schedule(candidates: list, budget_contacts: int, budget_calls: int, budget_spend: float):
    """
    candidates is a list of dicts: 
    { "event_id": ..., "arm": ..., "ev": ..., "cost": ..., "is_call": ..., "is_contact": ..., "item": ... }
    """
    # Sort by EV / max(cost, 0.01) descending
    candidates.sort(key=lambda c: c["ev"] / max(c["cost"], 0.01), reverse=True)
    
    selected = []
    deferred = []
    
    spent_contacts = 0
    spent_calls = 0
    spent_money = 0.0
    
    for c in candidates:
        can_afford_contact = not c["is_contact"] or (spent_contacts + 1 <= budget_contacts)
        can_afford_call = not c["is_call"] or (spent_calls + 1 <= budget_calls)
        can_afford_money = (spent_money + c["cost"] <= budget_spend)
        
        if can_afford_contact and can_afford_call and can_afford_money:
            selected.append(c)
            if c["is_contact"]: spent_contacts += 1
            if c["is_call"]: spent_calls += 1
            spent_money += c["cost"]
        else:
            deferred.append(c)
            
    return selected, deferred
