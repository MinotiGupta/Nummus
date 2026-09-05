from datetime import datetime

def build_context(event: dict, root_cause: str) -> str:
    """
    Constructs a discrete context key for the bandit.
    event dict must have: amount, tenure, timestamp
    """
    amount = event.get("amount", 0)
    
    # Amount Tier
    if amount < 2000:
        amount_tier = "low"
    elif amount < 10000:
        amount_tier = "med"
    else:
        amount_tier = "high"
        
    tenure_bucket = event.get("tenure", "unknown")
    
    # Day of week
    try:
        dt = datetime.fromisoformat(event.get("timestamp").replace("Z", "+00:00"))
        day_of_week = dt.strftime("%a").lower()
    except Exception:
        day_of_week = "unknown"
        
    # Example key: "insufficient_funds|med|returning|tue"
    context_key = f"{root_cause}|{amount_tier}|{tenure_bucket}|{day_of_week}"
    
    return context_key
