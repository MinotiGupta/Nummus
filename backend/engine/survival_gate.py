"""
survival_gate.py — Phase 4: Survival-Based Stopping & Escalation Gate

Implements the per-account stopping rule described in PRD §5.4.

Two decisions are made per event before the bandit is consulted:
  1. HOLD   — self-resolve probability is high enough; skip contact this cycle.
  2. FORCE  — max contact attempts reached; override bandit and escalate to human.
  3. PASS   — proceed to bandit arm selection normally.

Self-resolve score is a lightweight proxy for the Kaplan-Meier hazard concept
in the PRD. It is intentionally simple and explainable:
  - Base: 0.30 (reasonable prior — 30% of failures self-resolve)
  - Recency boost: fresh failures (< 1 day) are slightly more likely to
    self-resolve (customer may notice immediately).
  - Engagement decay: each completed contact attempt reduces the score
    (if we've already tried and they haven't resolved, they probably won't
    self-resolve now either).
  - Root-cause adjustment: "processor_error" has a higher base self-resolve
    rate (transient technical issues often fix themselves).

Stopping rule (PRD §5.4):
  if self_resolve_score > HOLD_THRESHOLD → hold, log reason
  elif contact_count >= MAX_ATTEMPTS     → force escalation

Standalone usage:
  python -m engine.survival_gate
"""

from .constants import HOLD_THRESHOLD, MAX_ATTEMPTS


# ─── Root-cause base self-resolve rates ──────────────────────────────────────
# Higher means more likely to resolve without contact.
_CAUSE_BASE_SCORE: dict[str, float] = {
    "insufficient_funds":   0.30,
    "expired_card":         0.15,  # unlikely to self-resolve — card needs updating
    "stolen_lost_card":     0.05,  # almost never self-resolves
    "issuer_decline_soft":  0.35,  # generic — often a transient issuer state
    "processor_error":      0.55,  # technical — frequently self-heals
    "bank_risk_hold":       0.20,
    "unknown":              0.25,
}

# Recency bonus: failures < 1 day old get a bump (customer may notice fast)
_RECENCY_BONUS   = 0.08
_RECENCY_DAYS    = 1

# Each outreach contact attempt lowers self-resolve expectation
_CONTACT_PENALTY = 0.06


def compute_self_resolve_score(account: dict, event: dict, root_cause: str) -> float:
    """
    Estimate the probability that this account will resolve the failure
    on its own without further contact this cycle.

    Args:
        account:    Account row dict from DB (fields: contact_count, last_action_at).
        event:      Event dict (fields: days_since_failure).
        root_cause: Classified root cause string.

    Returns:
        Float in [0.0, 1.0].
    """
    # Base rate from root-cause
    score = _CAUSE_BASE_SCORE.get(root_cause, 0.25)

    # Recency boost
    days = event.get("days_since_failure", 0)
    if days < _RECENCY_DAYS:
        score += _RECENCY_BONUS

    # Engagement decay per completed outreach contact
    contact_count = account.get("contact_count", 0)
    score -= _CONTACT_PENALTY * contact_count

    return round(max(0.0, min(1.0, score)), 4)


def should_hold(
    account: dict,
    event: dict,
    root_cause: str,
) -> tuple[bool, str | None]:
    """
    Evaluate the stopping and escalation rules for one account.

    Returns:
        (hold: bool, reason: str | None)

        hold=True  → do not contact this cycle; reason explains why.
        hold=False, reason=None       → proceed normally through bandit.
        hold=False, reason=<str>      → forced escalation; bandit is overridden
                                        by batch_runner to "escalate_human_call".
    """
    score         = compute_self_resolve_score(account, event, root_cause)
    contact_count = account.get("contact_count", 0)

    # Rule 1: High self-resolve probability → hold
    if score > HOLD_THRESHOLD:
        return True, f"gated: high self-resolve probability (p={score:.2f})"

    # Rule 2: Exhausted contact budget → force escalation
    if contact_count >= MAX_ATTEMPTS:
        return False, f"forced escalation: max attempts reached ({contact_count})"

    # Rule 3: Stolen/lost — immediately route to alternative, never wait
    if root_cause == "stolen_lost_card" and contact_count == 0:
        return False, None  # let bandit pick (retries are already filtered out)

    return False, None


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n--- survival_gate smoke tests ---\n")

    test_cases = [
        # Fresh processor_error, 0 contacts → should HOLD (score ≈ 0.63 > 0.70? No, 0.55+0.08=0.63, not > 0.70)
        # Actually 0.63 < 0.70 so it should PASS
        {
            "label": "processor_error, fresh, 0 contacts -> PASS (score ~0.63)",
            "account": {"contact_count": 0, "last_action_at": None},
            "event":   {"days_since_failure": 0},
            "cause":   "processor_error",
            "expect_hold": False,
        },
        # Issuer soft, fresh, 0 contacts -> PASS (0.35 + 0.08 = 0.43)
        {
            "label": "issuer_decline_soft, fresh, 0 contacts -> PASS (score ~0.43)",
            "account": {"contact_count": 0, "last_action_at": None},
            "event":   {"days_since_failure": 0},
            "cause":   "issuer_decline_soft",
            "expect_hold": False,
        },
        # Insufficient funds, 4 contacts -> FORCE ESCALATE
        {
            "label": "insufficient_funds, 4 contacts -> FORCE ESCALATE",
            "account": {"contact_count": 4, "last_action_at": "2026-09-01T12:00:00"},
            "event":   {"days_since_failure": 3},
            "cause":   "insufficient_funds",
            "expect_hold": False,
            "expect_reason_contains": "forced escalation",
        },
        # Expired card, 0 contacts, old failure -> PASS (0.15, no recency bonus)
        {
            "label": "expired_card, 5 days old, 0 contacts -> PASS (score 0.15)",
            "account": {"contact_count": 0, "last_action_at": None},
            "event":   {"days_since_failure": 5},
            "cause":   "expired_card",
            "expect_hold": False,
        },
    ]

    all_pass = True
    for tc in test_cases:
        score = compute_self_resolve_score(tc["account"], tc["event"], tc["cause"])
        hold, reason = should_hold(tc["account"], tc["event"], tc["cause"])

        ok = hold == tc["expect_hold"]
        if "expect_reason_contains" in tc:
            ok = ok and (reason and tc["expect_reason_contains"] in reason)

        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False

        print(f"  [{status}]  {tc['label']}")
        print(f"         score={score:.4f}  hold={hold}  reason={reason!r}\n")

    print(f"{'All tests passed!' if all_pass else 'SOME TESTS FAILED'}\n")
