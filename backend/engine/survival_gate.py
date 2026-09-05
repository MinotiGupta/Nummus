HOLD_THRESHOLD = 0.70
MAX_ATTEMPTS = 4

def compute_self_resolve_score(account: dict, event: dict) -> float:
    base = 0.3
    days_since = event.get("days_since_failure", 0)
    if days_since < 1:
        base += 0.1
        
    if account.get("last_action_at"):
        # Just a heuristic for now
        base += 0.1
        
    contact_count = account.get("contact_count", 0)
    base -= (0.05 * contact_count)
    
    return max(0.0, min(1.0, base))

def should_hold(account: dict, event: dict, root_cause: str):
    score = compute_self_resolve_score(account, event)
    contact_count = account.get("contact_count", 0)
    
    if score > HOLD_THRESHOLD:
        return True, f"gated: high self-resolve probability (p={score:.2f})"
        
    if contact_count >= MAX_ATTEMPTS:
        return False, "forced escalation: max attempts reached"
        
    return False, None
