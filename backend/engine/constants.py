"""
constants.py — Shared algorithm constants for the AI Revenue Recovery engine.

All tunable values live here so they can be referenced from data_generator,
executor (ground truth simulation), knapsack, and tests without circular imports.
"""

# ─── Decline code → root cause mapping ───────────────────────────────────────
DECLINE_CODES_MAP: dict[str, list[str]] = {
    "insufficient_funds":   ["51", "65", "61"],
    "expired_card":         ["54", "33"],
    "stolen_lost_card":     ["41", "43"],
    "issuer_decline_soft":  ["05", "12", "57"],
    "processor_error":      ["96", "91", "06"],
    "bank_risk_hold":       ["59", "62", "93"],
}

# Inverted map for O(1) lookup
CODE_TO_CAUSE: dict[str, str] = {
    code: cause
    for cause, codes in DECLINE_CODES_MAP.items()
    for code in codes
}

ROOT_CAUSES = list(DECLINE_CODES_MAP.keys())

# ─── Bandit arms ──────────────────────────────────────────────────────────────
ARMS: list[str] = [
    "retry_immediate",
    "retry_delayed_2h",
    "retry_delayed_24h",
    "offer_alt_payment_method",
    "send_reminder_email",
    "send_reminder_sms",
    "escalate_human_call",
    "hold_no_action",
]

# Arms that are retries — excluded when retryable=False
RETRY_ARMS = {"retry_immediate", "retry_delayed_2h", "retry_delayed_24h"}

# ─── Ground-truth simulation probabilities (hidden env) ──────────────────────
# These are the *true* success probabilities per (root_cause, arm) pair that
# the simulator draws from.  The bandit learns to discover these empirically.
# Deliberately separated so the best arm per context is clear for convergence demo.
GROUND_TRUTH: dict[tuple[str, str], float] = {
    # insufficient_funds: best arm is retry_delayed_24h (0.58) — clear winner
    ("insufficient_funds",  "retry_immediate"):           0.22,
    ("insufficient_funds",  "retry_delayed_2h"):          0.35,
    ("insufficient_funds",  "retry_delayed_24h"):         0.58,  # ← best
    ("insufficient_funds",  "offer_alt_payment_method"):  0.40,
    ("insufficient_funds",  "send_reminder_email"):       0.30,
    ("insufficient_funds",  "send_reminder_sms"):         0.45,
    ("insufficient_funds",  "escalate_human_call"):       0.25,
    ("insufficient_funds",  "hold_no_action"):            0.08,
    # expired_card: best arm is offer_alt_payment_method (0.72)
    ("expired_card",        "retry_immediate"):           0.05,
    ("expired_card",        "retry_delayed_2h"):          0.05,
    ("expired_card",        "retry_delayed_24h"):         0.05,
    ("expired_card",        "offer_alt_payment_method"):  0.72,  # ← best
    ("expired_card",        "send_reminder_email"):       0.55,
    ("expired_card",        "send_reminder_sms"):         0.50,
    ("expired_card",        "escalate_human_call"):       0.20,
    ("expired_card",        "hold_no_action"):            0.05,
    # stolen_lost_card: retries not allowed; best is offer_alt (0.30)
    ("stolen_lost_card",    "offer_alt_payment_method"):  0.30,  # ← best allowed
    ("stolen_lost_card",    "send_reminder_email"):       0.10,
    ("stolen_lost_card",    "send_reminder_sms"):         0.12,
    ("stolen_lost_card",    "escalate_human_call"):       0.20,
    ("stolen_lost_card",    "hold_no_action"):            0.02,
    # processor_error: best arm is retry_immediate (0.78) — technical failure
    ("processor_error",     "retry_immediate"):           0.78,  # ← best
    ("processor_error",     "retry_delayed_2h"):          0.65,
    ("processor_error",     "retry_delayed_24h"):         0.50,
    ("processor_error",     "offer_alt_payment_method"):  0.20,
    ("processor_error",     "send_reminder_email"):       0.10,
    ("processor_error",     "send_reminder_sms"):         0.10,
    ("processor_error",     "escalate_human_call"):       0.25,
    ("processor_error",     "hold_no_action"):            0.05,
    # issuer_decline_soft: best arm is retry_delayed_24h (0.48)
    ("issuer_decline_soft", "retry_immediate"):           0.18,
    ("issuer_decline_soft", "retry_delayed_2h"):          0.30,
    ("issuer_decline_soft", "retry_delayed_24h"):         0.48,  # ← best
    ("issuer_decline_soft", "offer_alt_payment_method"):  0.35,
    ("issuer_decline_soft", "send_reminder_email"):       0.28,
    ("issuer_decline_soft", "send_reminder_sms"):         0.32,
    ("issuer_decline_soft", "escalate_human_call"):       0.22,
    ("issuer_decline_soft", "hold_no_action"):            0.10,
    # bank_risk_hold: best arm is escalate_human_call (0.40)
    ("bank_risk_hold",      "retry_immediate"):           0.08,
    ("bank_risk_hold",      "retry_delayed_2h"):          0.10,
    ("bank_risk_hold",      "retry_delayed_24h"):         0.12,
    ("bank_risk_hold",      "offer_alt_payment_method"):  0.22,
    ("bank_risk_hold",      "send_reminder_email"):       0.15,
    ("bank_risk_hold",      "send_reminder_sms"):         0.18,
    ("bank_risk_hold",      "escalate_human_call"):       0.40,  # ← best
    ("bank_risk_hold",      "hold_no_action"):            0.06,
}

DEFAULT_SUCCESS_PROB = 0.10  # fallback for any (cause, arm) not in GROUND_TRUTH

# Fixed playbook used for baseline comparison (per root_cause → best static arm)
BASELINE_PLAYBOOK: dict[str, str] = {
    "insufficient_funds":   "retry_delayed_24h",
    "expired_card":         "send_reminder_email",   # naive baseline doesn't know offer is better
    "stolen_lost_card":     "offer_alt_payment_method",
    "processor_error":      "retry_immediate",
    "issuer_decline_soft":  "retry_delayed_24h",
    "bank_risk_hold":       "escalate_human_call",
}

# ─── Action costs (INR) ───────────────────────────────────────────────────────
ACTION_COSTS: dict[str, float] = {
    "retry_immediate":          0.0,
    "retry_delayed_2h":         0.0,
    "retry_delayed_24h":        0.0,
    "offer_alt_payment_method": 2.0,
    "send_reminder_email":      0.5,
    "send_reminder_sms":        0.5,
    "escalate_human_call":      150.0,
    "hold_no_action":           0.0,
}

# ─── Survival gate thresholds ────────────────────────────────────────────────
HOLD_THRESHOLD   = 0.70   # self-resolve probability above this → hold
MAX_ATTEMPTS     = 4       # escalate to human call after this many contacts

# ─── Knapsack budget defaults (per batch) ────────────────────────────────────
DAILY_CONTACT_BUDGET = 500   # max total contact actions per batch
DAILY_CALL_BUDGET    = 50    # max human-call escalations per batch
DAILY_SPEND_BUDGET   = 5000.0  # max INR spent on outreach per batch
