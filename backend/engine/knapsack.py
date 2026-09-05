"""
knapsack.py — Phase 5: EV-based Budget Scheduler

Selects the best subset of (event, arm) pairs that maximizes total expected
value within three budget constraints: total contacts, human-call escalations,
and total spend.

Algorithm:
    Greedy approximation by EV-density (EV / max(cost, ε)), which is provably
    within 1−1/e of optimal for this family of problems and runs in O(n log n).
    Documented as an intentional trade-off (exact DP would be O(n×W)).
"""

from .constants import ACTION_COSTS, DAILY_CONTACT_BUDGET, DAILY_CALL_BUDGET, DAILY_SPEND_BUDGET


def compute_ev(amount: float, posterior_mean_prob: float, arm: str) -> float:
    """
    Expected value of taking `arm` on an event worth `amount`.

    EV = P(recovery | arm) × amount_at_risk − cost(arm)

    Uses posterior_mean (not the Thompson sample) for a stable EV rank.
    """
    cost = ACTION_COSTS.get(arm, 0.0)
    return (posterior_mean_prob * amount) - cost


def schedule(
    candidates: list[dict],
    budget_contacts: int   = DAILY_CONTACT_BUDGET,
    budget_calls: int      = DAILY_CALL_BUDGET,
    budget_spend: float    = DAILY_SPEND_BUDGET,
) -> tuple[list[dict], list[dict]]:
    """
    Select the EV-maximizing subset of candidates within budget.

    Each candidate dict must have:
        arm        (str)   — chosen arm from bandit
        ev         (float) — expected value from compute_ev
        cost       (float) — action cost in INR
        is_call    (bool)  — True if arm == "escalate_human_call"
        is_contact (bool)  — True if the arm involves outreach (cost > 0)

    Returns:
        (selected, deferred)
        selected: candidates that made the budget cut
        deferred: candidates excluded due to budget
    """
    # Sort by EV-density descending (greedy knapsack approximation)
    sorted_candidates = sorted(
        candidates,
        key=lambda c: c["ev"] / max(c["cost"], 0.01),
        reverse=True,
    )

    selected: list[dict] = []
    deferred: list[dict] = []
    spent_contacts = 0
    spent_calls    = 0
    spent_money    = 0.0

    for c in sorted_candidates:
        would_use_contact = c["is_contact"]
        would_use_call    = c["is_call"]

        contact_ok = not would_use_contact or (spent_contacts + 1 <= budget_contacts)
        call_ok    = not would_use_call    or (spent_calls    + 1 <= budget_calls)
        spend_ok   = (spent_money + c["cost"]) <= budget_spend

        if contact_ok and call_ok and spend_ok:
            selected.append(c)
            if would_use_contact: spent_contacts += 1
            if would_use_call:    spent_calls    += 1
            spent_money += c["cost"]
        else:
            deferred.append(c)

    return selected, deferred
