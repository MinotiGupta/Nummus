DECLINE_CODES = {
    "insufficient_funds":   ["51", "65", "61"],
    "expired_card":         ["54", "33"],
    "stolen_lost_card":     ["41", "43"],
    "issuer_decline_soft":  ["05", "12", "57"],
    "processor_error":      ["96", "91", "06"],
    "bank_risk_hold":       ["59", "62", "93"],
}

CODE_TO_CAUSE = {}
for cause, codes in DECLINE_CODES.items():
    for code in codes:
        CODE_TO_CAUSE[code] = cause

def classify(decline_code: str):
    """
    Returns (root_cause: str, retryable: bool)
    """
    cause = CODE_TO_CAUSE.get(decline_code, "unknown")
    # By policy, stolen/lost cards are never retryable silently
    retryable = False if cause == "stolen_lost_card" else True
    return cause, retryable
