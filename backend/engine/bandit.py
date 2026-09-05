"""
bandit.py — Phase 3: Thompson Sampling Contextual Bandit

Implements a Beta-Binomial contextual bandit using Thompson Sampling.

Algorithm summary (PRD §5.3):
  - Each (context_key, arm) pair maintains a Beta distribution parameterised
    by (alpha, beta), initialised to Beta(1, 1) — a weak uniform prior.
  - At decision time, one sample is drawn from each eligible arm's Beta
    distribution.  The arm with the highest sample is selected.
  - After the outcome is observed, alpha += 1 (success) or beta += 1 (failure).
  - Over many events, the posterior of the best arm sharpens and its samples
    dominate, causing the policy to converge — provably and visibly.

Design choices:
  - scipy.stats.beta.rvs for sampling (vectorisable if needed at scale).
  - INSERT OR IGNORE for safe initialisation (idempotent across restarts).
  - get_posterior_means() uses alpha/(alpha+beta) for EV ranking — stable,
    not noisy like a Thompson sample.
  - All arm eligibility logic lives here (eligible_arms()) so batch_runner
    doesn't need to know compliance rules.

Standalone convergence test:
    python -m engine.bandit
"""

import datetime
import random
import scipy.stats
from sqlalchemy.orm import Session
from sqlalchemy import text

from .constants import ARMS, RETRY_ARMS, GROUND_TRUTH, DEFAULT_SUCCESS_PROB


# ─── Arm eligibility ──────────────────────────────────────────────────────────

def eligible_arms(root_cause: str, retryable: bool, forced_escalation: bool) -> list[str]:
    """
    Return the list of arms the bandit is allowed to sample from, given:
      - retryable:         False for stolen/lost cards (no silent retries, compliance rule)
      - forced_escalation: True when account has exhausted contact budget → human only

    Args:
        root_cause:         Root cause string (informational, not filtered here).
        retryable:          Whether retry arms are permitted.
        forced_escalation:  Whether to override all arms with escalate_human_call.

    Returns:
        Non-empty list of arm strings.
    """
    if forced_escalation:
        return ["escalate_human_call"]

    arms = list(ARMS)
    if not retryable:
        arms = [a for a in arms if a not in RETRY_ARMS]

    return arms


# ─── Posterior management ────────────────────────────────────────────────────

def get_posteriors(context_key: str, arms: list[str], db: Session) -> dict[str, dict]:
    """
    Load Beta posteriors for all arms in this context.
    Inserts uniform-prior rows (alpha=1, beta=1) for arms not yet seen.

    Returns:
        { arm: {"alpha": float, "beta": float} }
    """
    rows = db.execute(
        text("SELECT arm, alpha, beta FROM bandit_posteriors WHERE context_key = :ctx"),
        {"ctx": context_key},
    ).fetchall()

    posteriors = {row.arm: {"alpha": row.alpha, "beta": row.beta} for row in rows}

    # Initialise missing arms with the uniform prior
    new_rows = [
        {
            "context_key": context_key,
            "arm":         arm,
            "alpha":       1.0,
            "beta":        1.0,
            "updated_at":  datetime.datetime.utcnow().isoformat(),
        }
        for arm in arms
        if arm not in posteriors
    ]

    if new_rows:
        for arm in arms:
            if arm not in posteriors:
                posteriors[arm] = {"alpha": 1.0, "beta": 1.0}

        db.execute(
            text("""
                INSERT OR IGNORE INTO bandit_posteriors
                    (context_key, arm, alpha, beta, updated_at)
                VALUES
                    (:context_key, :arm, :alpha, :beta, :updated_at)
            """),
            new_rows,
        )
        db.commit()

    return posteriors


def get_posterior_means(context_key: str, db: Session) -> dict[str, float]:
    """
    Return the posterior mean E[p] = alpha / (alpha + beta) for every arm
    in this context.  Used by the knapsack scheduler for stable EV ranking
    (posterior mean is less noisy than a Thompson sample).
    """
    rows = db.execute(
        text("SELECT arm, alpha, beta FROM bandit_posteriors WHERE context_key = :ctx"),
        {"ctx": context_key},
    ).fetchall()
    return {
        row.arm: row.alpha / (row.alpha + row.beta)
        for row in rows
    }


def get_bandit_stats(context_key: str, db: Session) -> list[dict]:
    """
    Return rich per-arm statistics for a given context, sorted by posterior
    mean descending.  Powers the convergence view in the dashboard.

    Each item contains:
        arm             — arm name
        alpha           — Beta success count
        beta            — Beta failure count
        posterior_mean  — E[p] = alpha / (alpha + beta)
        n_trials        — total observations (alpha + beta - 2, discounting prior)
        ci_lower        — 5th percentile of posterior (uncertainty band)
        ci_upper        — 95th percentile of posterior
    """
    rows = db.execute(
        text("SELECT arm, alpha, beta FROM bandit_posteriors WHERE context_key = :ctx"),
        {"ctx": context_key},
    ).fetchall()

    stats = []
    for row in rows:
        a, b = row.alpha, row.beta
        dist = scipy.stats.beta(a, b)
        stats.append({
            "arm":            row.arm,
            "alpha":          a,
            "beta":           b,
            "posterior_mean": round(a / (a + b), 4),
            "n_trials":       int(a + b - 2),   # -2 removes the prior contribution
            "ci_lower":       round(float(dist.ppf(0.05)), 4),
            "ci_upper":       round(float(dist.ppf(0.95)), 4),
        })

    stats.sort(key=lambda x: x["posterior_mean"], reverse=True)
    return stats


# ─── Core bandit operations ───────────────────────────────────────────────────

def select_action(
    context_key: str,
    arms: list[str],
    db: Session,
) -> tuple[str | None, dict[str, float]]:
    """
    Thompson Sampling: draw one Beta sample per eligible arm,
    return the arm with the highest draw.

    Args:
        context_key: Discrete context string.
        arms:        Eligible arms (from eligible_arms()).
        db:          Active SQLAlchemy session.

    Returns:
        (chosen_arm, {arm: sampled_probability})
        chosen_arm is None only when arms is empty.
    """
    if not arms:
        return None, {}

    posteriors = get_posteriors(context_key, arms, db)

    best_arm    = None
    best_sample = -1.0
    sampled_probs: dict[str, float] = {}

    for arm in arms:
        a = posteriors[arm]["alpha"]
        b = posteriors[arm]["beta"]
        sample = float(scipy.stats.beta.rvs(a, b))
        sampled_probs[arm] = sample

        if sample > best_sample:
            best_sample = sample
            best_arm    = arm

    return best_arm, sampled_probs


def update_posterior(context_key: str, arm: str, success: bool, db: Session) -> None:
    """
    Bayesian update after observing an outcome.
      success=True  → alpha += 1
      success=False → beta  += 1
    """
    db.execute(
        text("""
            UPDATE bandit_posteriors
            SET alpha      = alpha + :d_alpha,
                beta       = beta  + :d_beta,
                updated_at = :now
            WHERE context_key = :ctx AND arm = :arm
        """),
        {
            "d_alpha": 1.0 if success else 0.0,
            "d_beta":  0.0 if success else 1.0,
            "now":     datetime.datetime.utcnow().isoformat(),
            "ctx":     context_key,
            "arm":     arm,
        },
    )
    db.commit()


# ─── In-memory convergence test ───────────────────────────────────────────────

class _InMemoryBandit:
    """
    Lightweight in-memory Beta-Binomial bandit for unit-testing convergence
    without a database.  Uses a plain dict as the posterior store.
    """

    def __init__(self, arms: list[str]):
        self.arms = arms
        self.posteriors: dict[str, dict] = {
            arm: {"alpha": 1.0, "beta": 1.0} for arm in arms
        }

    def sample(self) -> tuple[str, dict[str, float]]:
        best_arm    = None
        best_sample = -1.0
        samples: dict[str, float] = {}

        for arm in self.arms:
            a = self.posteriors[arm]["alpha"]
            b = self.posteriors[arm]["beta"]
            s = float(scipy.stats.beta.rvs(a, b))
            samples[arm] = s
            if s > best_sample:
                best_sample = s
                best_arm    = arm

        return best_arm, samples

    def update(self, arm: str, success: bool) -> None:
        if success:
            self.posteriors[arm]["alpha"] += 1.0
        else:
            self.posteriors[arm]["beta"] += 1.0

    def posterior_mean(self, arm: str) -> float:
        a = self.posteriors[arm]["alpha"]
        b = self.posteriors[arm]["beta"]
        return a / (a + b)

    def posterior_report(self) -> list[tuple[str, float, int]]:
        """Returns [(arm, mean, n_trials)] sorted by mean desc."""
        result = []
        for arm in self.arms:
            a = self.posteriors[arm]["alpha"]
            b = self.posteriors[arm]["beta"]
            result.append((arm, round(a / (a + b), 4), int(a + b - 2)))
        return sorted(result, key=lambda x: -x[1])


def _run_convergence_test(
    context: str = "insufficient_funds|med|returning",
    n_rounds: int = 300,
    seed: int = 42,
) -> bool:
    """
    Run an in-memory Thompson Sampling convergence test.

    Simulates `n_rounds` of:
      1. Sample arm from bandit.
      2. Draw outcome from GROUND_TRUTH table.
      3. Update bandit posterior.

    Then verify that the top-ranked arm by posterior mean matches the
    ground-truth best arm for this (root_cause, arm) pair.

    Returns True if the bandit converged to the correct arm.
    """
    rng = random.Random(seed)

    # Extract root_cause from context key (first segment)
    root_cause = context.split("|")[0]

    # Determine which arms are eligible (no retries for stolen/lost)
    arms = list(ARMS)
    if root_cause == "stolen_lost_card":
        arms = [a for a in arms if a not in RETRY_ARMS]

    # Find true best arm from GROUND_TRUTH
    best_true_arm = max(
        arms,
        key=lambda a: GROUND_TRUTH.get((root_cause, a), DEFAULT_SUCCESS_PROB),
    )
    best_true_prob = GROUND_TRUTH.get((root_cause, best_true_arm), DEFAULT_SUCCESS_PROB)

    bandit = _InMemoryBandit(arms)

    print(f"\n  Context :  {context}")
    print(f"  Arms    :  {len(arms)}")
    print(f"  Best arm:  {best_true_arm} (ground-truth p={best_true_prob:.2f})")
    print(f"  Rounds  :  {n_rounds}\n")

    # Print progress every 50 rounds
    checkpoints = [50, 100, 200, n_rounds]
    checkpoint_set = set(checkpoints)

    for i in range(1, n_rounds + 1):
        arm, _ = bandit.sample()
        prob    = GROUND_TRUTH.get((root_cause, arm), DEFAULT_SUCCESS_PROB)
        outcome = rng.random() < prob
        bandit.update(arm, outcome)

        if i in checkpoint_set:
            top = bandit.posterior_report()
            print(f"  After {i:>3} rounds:")
            for rank, (a, mean, trials) in enumerate(top[:3], 1):
                marker = " <-- BEST" if a == best_true_arm else ""
                print(f"    #{rank}  {a:<30}  mean={mean:.4f}  trials={trials}{marker}")
            print()

    final_top_arm = bandit.posterior_report()[0][0]
    converged = (final_top_arm == best_true_arm)
    print(f"  Converged to correct arm: {'YES' if converged else 'NO'}")
    print(f"  Final top arm: {final_top_arm}")
    return converged


# ─── Standalone entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Phase 3 — Bandit Convergence Test (in-memory)")
    print("=" * 60)

    test_contexts = [
        "insufficient_funds|med|returning",
        "expired_card|high|loyal",
        "processor_error|low|new",
        "bank_risk_hold|med|returning",
    ]

    results = []
    for ctx in test_contexts:
        ok = _run_convergence_test(ctx, n_rounds=300, seed=42)
        results.append((ctx, ok))
        print("-" * 60)

    print("\n  Summary:")
    all_pass = True
    for ctx, ok in results:
        status = "CONVERGED" if ok else "FAILED"
        if not ok:
            all_pass = False
        print(f"    [{status}]  {ctx}")

    print(f"\n  {'ALL CONTEXTS CONVERGED' if all_pass else 'SOME FAILED TO CONVERGE'}\n")
