"""
context_builder.py — Phase 2: Context Vector Builder

Converts a raw payment-failure event into a discrete context key string
that the bandit uses to look up its (context, arm) posterior distributions.

Design rationale (from PRD §5.2):
  Contexts are deliberately coarse (bucketed, not continuous) so the bandit
  has enough events per context to learn quickly within a buildathon-scale
  dataset. This is a stated design trade-off favouring fast convergence and
  explainability over granularity.

Context key format:
  "{root_cause}|{amount_tier}|{tenure}|{day_of_week}"

  Example: "insufficient_funds|med|returning|tue"

Amount tiers (INR):
  low  → amount < 2,000
  med  → 2,000 ≤ amount < 10,000
  high → amount ≥ 10,000

Standalone usage:
  python -m engine.context_builder
"""

from datetime import datetime, timezone
from typing import Optional


# ─── Bucketing thresholds ─────────────────────────────────────────────────────

AMOUNT_TIERS = [
    (2_000,  "low"),
    (10_000, "med"),
    (float("inf"), "high"),
]


def _amount_tier(amount: float) -> str:
    """Discretise amount into a low/med/high tier."""
    for threshold, label in AMOUNT_TIERS:
        if amount < threshold:
            return label
    return "high"


def _day_of_week(timestamp_str: Optional[str]) -> str:
    """
    Parse an ISO-8601 timestamp and return a three-letter day abbreviation
    (mon, tue, wed, thu, fri, sat, sun).  Returns "unknown" on any parse error.
    """
    if not timestamp_str:
        return "unknown"
    try:
        # Handle both offset-aware ("+00:00") and naive timestamps
        ts = timestamp_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%a").lower()
    except (ValueError, TypeError):
        return "unknown"


# ─── Public API ───────────────────────────────────────────────────────────────

def build_context(event: dict, root_cause: str) -> str:
    """
    Build a discrete context key for the bandit from a raw event dict.

    Required event fields:
        amount    (float)  — transaction amount in INR
        tenure    (str)    — one of: new / returning / loyal
        timestamp (str)    — ISO-8601 failure timestamp

    Args:
        event:      Event dict (from data_generator or DB row).
        root_cause: Pre-classified root cause string.

    Returns:
        Context key string, e.g. "insufficient_funds|med|returning|tue"
    """
    tier    = _amount_tier(float(event.get("amount", 0)))
    tenure  = event.get("tenure", "unknown")
    day     = _day_of_week(event.get("timestamp"))

    return f"{root_cause}|{tier}|{tenure}|{day}"


def decode_context(context_key: str) -> dict:
    """
    Parse a context key back into its component fields.
    Useful for the dashboard's convergence view labels.

    Returns:
        { root_cause, amount_tier, tenure, day_of_week }
        Any missing parts default to "unknown".
    """
    parts = context_key.split("|")
    return {
        "root_cause":   parts[0] if len(parts) > 0 else "unknown",
        "amount_tier":  parts[1] if len(parts) > 1 else "unknown",
        "tenure":       parts[2] if len(parts) > 2 else "unknown",
        "day_of_week":  parts[3] if len(parts) > 3 else "unknown",
    }


def context_label(context_key: str) -> str:
    """
    Human-readable one-line label for a context key.
    E.g. "Insufficient Funds · Med · Returning · Tue"
    """
    parts = decode_context(context_key)
    cause  = parts["root_cause"].replace("_", " ").title()
    tier   = parts["amount_tier"].title()
    tenure = parts["tenure"].title()
    day    = parts["day_of_week"].title()
    return f"{cause} · {tier} · {tenure} · {day}"


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        # (event_dict, root_cause, expected_key_prefix)
        (
            {"amount": 1500,  "tenure": "new",       "timestamp": "2026-09-02T10:00:00+00:00"},
            "insufficient_funds",
            "insufficient_funds|low|new|",
        ),
        (
            {"amount": 5000,  "tenure": "returning",  "timestamp": "2026-09-03T15:30:00+00:00"},
            "expired_card",
            "expired_card|med|returning|",
        ),
        (
            {"amount": 25000, "tenure": "loyal",      "timestamp": "2026-09-04T08:00:00+00:00"},
            "bank_risk_hold",
            "bank_risk_hold|high|loyal|",
        ),
        (
            {"amount": 999,   "tenure": "new",        "timestamp": None},          # missing timestamp
            "processor_error",
            "processor_error|low|new|unknown",
        ),
    ]

    print("\n--- context_builder smoke tests ---\n")
    all_pass = True
    for event, cause, expected_prefix in test_cases:
        key   = build_context(event, cause)
        label = context_label(key)
        ok    = key.startswith(expected_prefix)
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}]  {key}")
        print(f"         Label : {label}")
        print(f"         Decode: {decode_context(key)}\n")

    # Amount tier boundary checks
    print("--- Amount tier boundaries ---")
    for amt, expected in [(0, "low"), (1999, "low"), (2000, "med"), (9999, "med"), (10000, "high"), (50000, "high")]:
        tier = _amount_tier(amt)
        ok   = tier == expected
        print(f"  {'PASS' if ok else 'FAIL'}  INR {amt:>6} -> {tier}")

    print(f"\n{'All tests passed!' if all_pass else 'SOME TESTS FAILED'}\n")
