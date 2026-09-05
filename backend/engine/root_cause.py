"""
root_cause.py — Phase 2: Deterministic Root Cause Classifier

Maps a decline code to a root-cause bucket and sets the retryable flag.
Pure function — no DB, no side effects.
"""

from .constants import CODE_TO_CAUSE


def classify(decline_code: str) -> tuple[str, bool]:
    """
    Classify a payment failure decline code.

    Args:
        decline_code: Two-digit ISO 8583 decline code (e.g. "51", "41").

    Returns:
        (root_cause, retryable)
        - root_cause: one of the six canonical buckets, or "unknown"
        - retryable:  False for stolen/lost cards (compliance rule); True otherwise
    """
    cause = CODE_TO_CAUSE.get(decline_code, "unknown")
    retryable = cause != "stolen_lost_card"
    return cause, retryable
