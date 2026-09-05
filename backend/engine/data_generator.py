"""
data_generator.py — Phase 1: Synthetic Dataset Generator

Generates a realistic batch of payment-failure events for the AI Revenue
Recovery engine.  Also exposes a baseline simulator that runs the fixed
playbook on the same events (for fair before/after comparison).

Design decisions:
- Account pool is smaller than event count so accounts *repeat* across batches,
  simulating real account history accumulation.
- Amounts follow a log-normal distribution calibrated for Indian payments
  (median ~₹1,800, long tail up to ₹50,000).
- Decline code distribution matches rough real-world proportions:
  insufficient_funds dominant, stolen/lost rare.
- days_since_failure is skewed toward recent (0–3 days) to make the
  survival gate's timing signal meaningful.
- Tenure and region are correlated weakly with amount to create realistic
  heterogeneity for the bandit's context buckets.

Standalone usage:
    python -m engine.data_generator          # prints 5 sample events
    python -m engine.data_generator --n 200  # prints summary stats
"""

import uuid
import random
import math
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from .constants import (
    DECLINE_CODES_MAP,
    CODE_TO_CAUSE,
    GROUND_TRUTH,
    DEFAULT_SUCCESS_PROB,
    BASELINE_PLAYBOOK,
)

# ─── Sampling weights ─────────────────────────────────────────────────────────
# (root_cause, weight) — must sum to ~1; reflects realistic card-failure mix
CAUSE_WEIGHTS = [
    ("insufficient_funds",  0.40),
    ("expired_card",        0.15),
    ("stolen_lost_card",    0.04),
    ("issuer_decline_soft", 0.22),
    ("processor_error",     0.10),
    ("bank_risk_hold",      0.09),
]
_CAUSE_NAMES   = [c for c, _ in CAUSE_WEIGHTS]
_CAUSE_PROBS   = [w for _, w in CAUSE_WEIGHTS]

# Tenure weights
TENURE_CHOICES  = ["new", "returning", "loyal"]
TENURE_WEIGHTS  = [0.30, 0.45, 0.25]

REGION_CHOICES  = ["north", "south", "west", "east"]
REGION_WEIGHTS  = [0.25, 0.25, 0.30, 0.20]  # west (Mumbai/Pune) slightly higher

# days_since_failure — skewed toward recent
DAYS_WEIGHTS = [0.30, 0.22, 0.15, 0.10, 0.07, 0.05, 0.04, 0.03, 0.02, 0.01, 0.01]
DAYS_VALUES  = list(range(11))


def _sample_amount(rng: random.Random, tenure: str) -> float:
    """
    Log-normal amount in INR.
    Loyal customers skew higher (median ~₹3,500) than new (median ~₹900).
    """
    mu_map = {"new": 6.8, "returning": 7.4, "loyal": 8.0}
    mu = mu_map.get(tenure, 7.4)
    raw = rng.lognormvariate(mu, 0.9)
    # Clamp to sensible range: ₹50 – ₹50,000
    return round(max(50.0, min(raw, 50_000.0)), 2)


def _sample_account_id(rng: random.Random, pool_size: int) -> str:
    """
    Pick from a finite pool so accounts repeat realistically across batches.
    Pool size defaults to ~40% of batch size to create meaningful history.
    """
    return f"acc_{rng.randint(1000, 1000 + pool_size - 1):04d}"


def generate_batch(
    n: int = 200,
    seed: Optional[int] = None,
    account_pool_size: Optional[int] = None,
) -> list[dict]:
    """
    Generate `n` synthetic payment-failure events.

    Args:
        n:                  Number of events.
        seed:               Optional RNG seed for reproducibility.
        account_pool_size:  Number of distinct accounts to draw from.
                            Defaults to max(50, n // 5), so accounts repeat.

    Returns:
        List of event dicts ready for DB insertion and pipeline processing.
        Each dict contains all fields the pipeline stages expect.
    """
    rng = random.Random(seed)

    if account_pool_size is None:
        account_pool_size = max(50, n // 5)

    now_utc = datetime.now(timezone.utc)
    events: list[dict] = []

    for _ in range(n):
        # 1. Sample root cause + decline code
        cause = rng.choices(_CAUSE_NAMES, weights=_CAUSE_PROBS, k=1)[0]
        decline_code = rng.choice(DECLINE_CODES_MAP[cause])

        # 2. Sample customer metadata
        tenure = rng.choices(TENURE_CHOICES, weights=TENURE_WEIGHTS, k=1)[0]
        region = rng.choices(REGION_CHOICES, weights=REGION_WEIGHTS, k=1)[0]

        # 3. Amount
        amount = _sample_amount(rng, tenure)

        # 4. Timing — skew toward recent failures
        days_ago = rng.choices(DAYS_VALUES, weights=DAYS_WEIGHTS, k=1)[0]
        hours_ago = rng.randint(0, 23)
        failure_ts = now_utc - timedelta(days=days_ago, hours=hours_ago)

        # 5. Retryable flag (stolen/lost cards are never silently retried)
        retryable = cause != "stolen_lost_card"

        events.append({
            "event_id":           str(uuid.uuid4()),
            "account_id":         _sample_account_id(rng, account_pool_size),
            "event_type":         "payment_failure",
            "amount":             amount,
            "currency":           "INR",
            "decline_code":       decline_code,
            "timestamp":          failure_ts.isoformat(),
            # ── pipeline fields (populated by later stages too) ──────────
            "root_cause":         cause,
            "retryable":          retryable,
            "tenure":             tenure,
            "region":             region,
            "days_since_failure": days_ago,
        })

    return events


def simulate_baseline(events: list[dict]) -> dict:
    """
    Run the fixed baseline playbook against a batch of events and return
    aggregate recovery statistics.

    This is computed once at batch-generation time so the comparison number
    is locked in before the bandit runs — preventing cherry-picking.

    The baseline uses a separate RNG seeded from the event IDs so results
    are deterministic per batch but independent from the main bandit RNG.

    Returns:
        {
          "total_at_risk":       float,   # sum of all event amounts
          "baseline_recovered":  float,   # sum recovered by fixed playbook
          "baseline_rate":       float,   # recovered / at_risk  (0..1)
          "per_event":           list[dict]  # one row per event
        }
    """
    total_at_risk = 0.0
    baseline_recovered = 0.0
    per_event = []

    for e in events:
        cause = e["root_cause"]
        amount = e["amount"]
        total_at_risk += amount

        arm = BASELINE_PLAYBOOK.get(cause, "send_reminder_email")

        # Don't apply retry arms to non-retryable events
        if not e.get("retryable", True) and arm.startswith("retry"):
            arm = "offer_alt_payment_method"

        prob = GROUND_TRUTH.get((cause, arm), DEFAULT_SUCCESS_PROB)

        # Deterministic per-event outcome seeded from event_id for reproducibility
        local_rng = random.Random(e["event_id"])
        outcome = local_rng.random() < prob
        recovered = amount if outcome else 0.0

        baseline_recovered += recovered
        per_event.append({
            "event_id":        e["event_id"],
            "baseline_arm":    arm,
            "baseline_prob":   prob,
            "baseline_outcome": outcome,
            "recovered":       recovered,
        })

    rate = baseline_recovered / total_at_risk if total_at_risk > 0 else 0.0
    return {
        "total_at_risk":      total_at_risk,
        "baseline_recovered": baseline_recovered,
        "baseline_rate":      rate,
        "per_event":          per_event,
    }


def print_summary(events: list[dict], baseline: dict) -> None:
    """Print a human-readable summary to stdout (for CLI / standalone test)."""
    from collections import Counter

    cause_counts = Counter(e["root_cause"] for e in events)
    tenure_counts = Counter(e["tenure"] for e in events)
    amounts = [e["amount"] for e in events]

    SEP = "=" * 60
    LINE = "-" * 60
    print(f"\n{SEP}")
    print(f"  Batch size:        {len(events)} events")
    print(f"  Unique accounts:   {len({e['account_id'] for e in events})}")
    print(f"  Amount at risk:    INR {baseline['total_at_risk']:,.2f}")
    print(f"  Median amount:     INR {sorted(amounts)[len(amounts)//2]:,.2f}")
    print(f"  Baseline recovery: INR {baseline['baseline_recovered']:,.2f}  ({baseline['baseline_rate']*100:.1f}%)")
    print(LINE)
    print("  Root cause distribution:")
    for cause, cnt in sorted(cause_counts.items(), key=lambda x: -x[1]):
        bar = "#" * int(cnt / len(events) * 40)
        print(f"    {cause:<25} {cnt:>4}  {bar}")
    print(LINE)
    print("  Tenure distribution:")
    for tenure, cnt in tenure_counts.items():
        print(f"    {tenure:<12} {cnt:>4}")
    print(f"{SEP}\n")


# ─── Standalone entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synthetic event generator — Phase 1")
    parser.add_argument("--n",    type=int, default=200, help="Number of events to generate")
    parser.add_argument("--seed", type=int, default=42,  help="RNG seed (default 42)")
    parser.add_argument("--json", action="store_true",   help="Print first 5 events as JSON")
    args = parser.parse_args()

    print(f"\nGenerating {args.n} synthetic payment-failure events (seed={args.seed}) ...")
    batch = generate_batch(n=args.n, seed=args.seed)
    baseline = simulate_baseline(batch)

    if args.json:
        print(json.dumps(batch[:5], indent=2, default=str))
    else:
        print_summary(batch, baseline)
