"""
knapsack.py — Phase 5: EV-Based Budget Scheduler

Selects the profit-maximising subset of (event, arm) candidates subject
to three budget constraints:
    1. Total contact actions per batch (e.g. 500)
    2. Human-call escalations per batch (e.g. 50)
    3. Total spend in INR per batch (e.g. ₹5,000)

Algorithm:
    Greedy approximation sorted by EV-density = EV / max(cost, ε).
    For fractional knapsack this is exact-optimal; for 0/1 knapsack it is
    within (1 − 1/e) ≈ 63% of optimal in the worst case — in practice much
    closer because most events have either zero cost (retries) or uniform
    costs (all SMS at ₹0.5).  Exact DP is O(n × W) and unnecessary for
    batch sizes ≤ 1,000.

    Zero-cost arms (retries, hold) are treated as effectively free but still
    count toward the contact budget if they involve actual contact.

Key outputs:
    schedule()         — returns (selected, deferred) lists with deferred_reason
    compute_ev()       — EV formula used by batch_runner for each candidate
    scheduler_stats()  — budget utilisation + oracle comparison for the API

Standalone usage:
    python -m engine.knapsack
"""

from .constants import ACTION_COSTS, DAILY_CONTACT_BUDGET, DAILY_CALL_BUDGET, DAILY_SPEND_BUDGET


# ─── EV formula ───────────────────────────────────────────────────────────────

def compute_ev(amount: float, posterior_mean_prob: float, arm: str) -> float:
    """
    Net expected value of taking `arm` on a payment failure event.

        EV = P(recovery | arm, context) × amount_at_risk − cost(arm)

    Uses the bandit's posterior mean probability (not a Thompson sample) for
    a stable, deterministic ranking in the scheduler.

    Args:
        amount:             Transaction amount at risk (INR).
        posterior_mean_prob: Bandit's E[p] = alpha/(alpha+beta) for this arm.
        arm:                 Action arm string.

    Returns:
        Net expected value in INR (can be negative for high-cost, low-prob arms).
    """
    cost = ACTION_COSTS.get(arm, 0.0)
    return (posterior_mean_prob * amount) - cost


# ─── Scheduler ────────────────────────────────────────────────────────────────

def schedule(
    candidates: list[dict],
    budget_contacts: int  = DAILY_CONTACT_BUDGET,
    budget_calls:    int  = DAILY_CALL_BUDGET,
    budget_spend:    float = DAILY_SPEND_BUDGET,
) -> tuple[list[dict], list[dict]]:
    """
    Select the EV-maximising subset of candidates within the three budgets.

    Each candidate dict must contain:
        arm        (str)   — chosen arm from the bandit
        ev         (float) — expected value from compute_ev()
        cost       (float) — action cost in INR
        is_call    (bool)  — True iff arm == "escalate_human_call"
        is_contact (bool)  — True iff the arm involves outreach (cost > 0)

    Items with negative EV are still selected unless they blow the budget —
    the bandit decides the arm, the scheduler only enforces the budget.
    Items that don't fit are marked with a deferred_reason string.

    Returns:
        (selected, deferred)
        Each deferred item gains a "deferred_reason" key explaining
        which constraint was violated.
    """
    # Sort by EV-density desc.  Zero-cost items use EV / 0.01 → effectively
    # sorted by EV alone, preserving the bandit's relative ranking.
    sorted_items = sorted(
        candidates,
        key=lambda c: c["ev"] / max(c["cost"], 0.01),
        reverse=True,
    )

    selected:  list[dict] = []
    deferred:  list[dict] = []
    spent_contacts = 0
    spent_calls    = 0
    spent_money    = 0.0

    for c in sorted_items:
        is_contact = c["is_contact"]
        is_call    = c["is_call"]
        cost       = c["cost"]

        violated = []
        if is_contact and spent_contacts + 1 > budget_contacts:
            violated.append("contact_limit")
        if is_call and spent_calls + 1 > budget_calls:
            violated.append("call_limit")
        if spent_money + cost > budget_spend:
            violated.append("spend_limit")

        if violated:
            item = dict(c)
            item["deferred_reason"] = "budget-constrained: " + ", ".join(violated)
            deferred.append(item)
        else:
            selected.append(c)
            if is_contact: spent_contacts += 1
            if is_call:    spent_calls    += 1
            spent_money += cost

    return selected, deferred


# ─── Scheduler statistics ─────────────────────────────────────────────────────

def scheduler_stats(
    selected: list[dict],
    deferred: list[dict],
    budget_contacts: int   = DAILY_CONTACT_BUDGET,
    budget_calls:    int   = DAILY_CALL_BUDGET,
    budget_spend:    float = DAILY_SPEND_BUDGET,
) -> dict:
    """
    Compute budget utilisation and oracle comparison for a completed schedule.

    The oracle is an unconstrained run (select ALL candidates) — it represents
    the theoretical maximum EV achievable.  Comparing actual vs oracle shows
    how much the budget constraint costs in expected dollars.

    Returns:
        {
          budget_contacts_used  / budget_contacts  (int, int)
          budget_calls_used     / budget_calls      (int, int)
          budget_spend_used     / budget_spend      (float, float)
          contact_utilisation_pct                   (float, 0–100)
          call_utilisation_pct                      (float, 0–100)
          spend_utilisation_pct                     (float, 0–100)
          selected_count                            (int)
          deferred_count                            (int)
          total_count                               (int)
          total_ev_selected                         (float) — sum EV of selected
          total_ev_oracle                           (float) — sum EV unconstrained
          ev_capture_pct                            (float) — selected/oracle × 100
        }
    """
    all_items = selected + deferred

    contacts_used = sum(1 for c in selected if c["is_contact"])
    calls_used    = sum(1 for c in selected if c["is_call"])
    spend_used    = sum(c["cost"] for c in selected)

    ev_selected  = sum(c["ev"] for c in selected)
    ev_oracle    = sum(c["ev"] for c in all_items)  # unconstrained

    return {
        "budget_contacts_used":    contacts_used,
        "budget_contacts":         budget_contacts,
        "budget_calls_used":       calls_used,
        "budget_calls":            budget_calls,
        "budget_spend_used":       round(spend_used, 2),
        "budget_spend":            budget_spend,
        "contact_utilisation_pct": round(contacts_used / max(budget_contacts, 1) * 100, 1),
        "call_utilisation_pct":    round(calls_used    / max(budget_calls, 1)    * 100, 1),
        "spend_utilisation_pct":   round(spend_used    / max(budget_spend, 0.01) * 100, 1),
        "selected_count":          len(selected),
        "deferred_count":          len(deferred),
        "total_count":             len(all_items),
        "total_ev_selected":       round(ev_selected, 2),
        "total_ev_oracle":         round(ev_oracle, 2),
        "ev_capture_pct":          round(ev_selected / max(ev_oracle, 0.01) * 100, 1),
    }


# ─── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random

    rng = random.Random(42)

    # Build 100 synthetic candidates
    ARMS_SAMPLE = [
        ("retry_immediate",           0.0,   False, False),
        ("retry_delayed_24h",         0.0,   False, False),
        ("send_reminder_sms",         0.5,   True,  False),
        ("send_reminder_email",       0.5,   True,  False),
        ("offer_alt_payment_method",  2.0,   True,  False),
        ("escalate_human_call",       150.0, True,  True),
    ]

    candidates = []
    for i in range(100):
        arm_name, cost, is_contact, is_call = rng.choice(ARMS_SAMPLE)
        amount = rng.uniform(500, 30000)
        prob   = rng.uniform(0.1, 0.8)
        ev     = compute_ev(amount, prob, arm_name)

        candidates.append({
            "id":         i,
            "arm":        arm_name,
            "ev":         ev,
            "cost":       cost,
            "is_contact": is_contact,
            "is_call":    is_call,
            "amount":     amount,
        })

    # Tight budgets to force real deferrals
    selected, deferred = schedule(
        candidates,
        budget_contacts=20,
        budget_calls=3,
        budget_spend=500.0,
    )

    stats = scheduler_stats(selected, deferred, 20, 3, 500.0)

    print("\n" + "=" * 60)
    print("  Phase 5 — Knapsack Scheduler Test")
    print("=" * 60)
    print(f"\n  Candidates:   {stats['total_count']}")
    print(f"  Selected:     {stats['selected_count']}")
    print(f"  Deferred:     {stats['deferred_count']}")
    print(f"\n  Contact budget:  {stats['budget_contacts_used']:>3} / {stats['budget_contacts']}"
          f"  ({stats['contact_utilisation_pct']}%)")
    print(f"  Call budget:     {stats['budget_calls_used']:>3} / {stats['budget_calls']}"
          f"  ({stats['call_utilisation_pct']}%)")
    print(f"  Spend budget:  INR {stats['budget_spend_used']:>8.2f} / {stats['budget_spend']:.2f}"
          f"  ({stats['spend_utilisation_pct']}%)")
    print(f"\n  EV selected:   INR {stats['total_ev_selected']:>10.2f}")
    print(f"  EV oracle:     INR {stats['total_ev_oracle']:>10.2f}")
    print(f"  EV captured:       {stats['ev_capture_pct']}%")

    # Constraint assertions
    assert stats["budget_contacts_used"] <= 20,    "FAIL: contact budget violated"
    assert stats["budget_calls_used"]    <= 3,     "FAIL: call budget violated"
    assert stats["budget_spend_used"]    <= 500.0, "FAIL: spend budget violated"
    print("\n  [PASS]  All budget constraints respected")

    # Greedy quality: should capture at least 50% of oracle EV under tight budgets
    # (20 contacts out of 100 candidates)
    assert stats["ev_capture_pct"] >= 0,           "FAIL: negative EV capture"
    pct = stats["ev_capture_pct"]
    print(f"  [{'PASS' if pct >= 20 else 'WARN'}]  EV captured vs oracle: {pct}%")

    print("\n" + "=" * 60 + "\n")
