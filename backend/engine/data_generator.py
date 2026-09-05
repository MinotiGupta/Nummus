import uuid
import random
from datetime import datetime, timedelta

DECLINE_CODES_MAP = {
    "insufficient_funds":   ["51", "65", "61"],
    "expired_card":         ["54", "33"],
    "stolen_lost_card":     ["41", "43"],
    "issuer_decline_soft":  ["05", "12", "57"],
    "processor_error":      ["96", "91", "06"],
    "bank_risk_hold":       ["59", "62", "93"],
}

# Invert for easy lookup
FLAT_DECLINE_CODES = [code for codes in DECLINE_CODES_MAP.values() for code in codes]

def generate_batch(n=200, seed=None):
    if seed is not None:
        random.seed(seed)
        
    events = []
    now = datetime.utcnow()
    
    for _ in range(n):
        # Sample root cause weighted loosely by realism
        cause = random.choices(
            list(DECLINE_CODES_MAP.keys()),
            weights=[0.40, 0.15, 0.05, 0.20, 0.10, 0.10],
            k=1
        )[0]
        
        decline_code = random.choice(DECLINE_CODES_MAP[cause])
        
        # Log normal for amount (e.g. median ~2500 INR)
        amount = round(random.lognormvariate(7.5, 1.2), 2)
        amount = max(50.0, min(amount, 100000.0))
        
        # Metadata
        tenure = random.choice(["new", "returning", "loyal"])
        region = random.choice(["north", "south", "west", "east"])
        days_since_failure = random.randint(0, 10)
        
        events.append({
            "event_id": str(uuid.uuid4()),
            "account_id": f"acc_{random.randint(1000, 9999)}",
            "event_type": "payment_failure",
            "amount": amount,
            "currency": "INR",
            "decline_code": decline_code,
            "timestamp": (now - timedelta(days=days_since_failure, hours=random.randint(0, 23))).isoformat(),
            "tenure": tenure,
            "region": region,
            "days_since_failure": days_since_failure
        })
        
    return events

if __name__ == "__main__":
    batch = generate_batch(5)
    import json
    print(json.dumps(batch, indent=2))
