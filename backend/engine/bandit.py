"""
bandit.py — Phase 3: Thompson Sampling Contextual Bandit

Beta-Binomial Thompson Sampling engine.  One (context_key, arm) row in
bandit_posteriors per distinct context seen.  Initialized with a weak
uniform prior (alpha=1, beta=1).

Key functions:
    select_action  — draw a Thompson sample per arm, return best arm + all samples
    update_posterior — update alpha/beta after an observed outcome
"""

import datetime
import scipy.stats
from sqlalchemy.orm import Session
from sqlalchemy import text

from .constants import ARMS


def get_posteriors(context_key: str, eligible_arms: list[str], db: Session) -> dict:
    """
    Load posteriors for all eligible arms in this context.
    Inserts default rows (alpha=1, beta=1) for any arm not yet seen.

    Returns:
        { arm: {"alpha": float, "beta": float} }
    """
    rows = db.execute(
        text("SELECT arm, alpha, beta FROM bandit_posteriors WHERE context_key = :ctx"),
        {"ctx": context_key},
    ).fetchall()

    posteriors = {row.arm: {"alpha": row.alpha, "beta": row.beta} for row in rows}

    # Insert defaults for arms we have no data on yet
    new_rows = []
    for arm in eligible_arms:
        if arm not in posteriors:
            posteriors[arm] = {"alpha": 1.0, "beta": 1.0}
            new_rows.append({
                "context_key": context_key,
                "arm":         arm,
                "alpha":       1.0,
                "beta":        1.0,
                "updated_at":  datetime.datetime.utcnow().isoformat(),
            })

    if new_rows:
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


def select_action(
    context_key: str,
    eligible_arms: list[str],
    db: Session,
) -> tuple[str | None, dict[str, float]]:
    """
    Thompson Sampling: draw Beta(alpha, beta) for each eligible arm,
    return the arm with the highest sample.

    Args:
        context_key:   Discrete context string (from context_builder).
        eligible_arms: Arms the compliance/retryable filter allows.
        db:            Active SQLAlchemy session.

    Returns:
        (chosen_arm, {arm: sampled_probability})
        chosen_arm is None only if eligible_arms is empty.
    """
    if not eligible_arms:
        return None, {}

    posteriors = get_posteriors(context_key, eligible_arms, db)

    best_arm: str | None = None
    best_sample = -1.0
    sampled_probs: dict[str, float] = {}

    for arm in eligible_arms:
        alpha = posteriors[arm]["alpha"]
        beta  = posteriors[arm]["beta"]
        sample = float(scipy.stats.beta.rvs(alpha, beta))
        sampled_probs[arm] = sample

        if sample > best_sample:
            best_sample = sample
            best_arm    = arm

    return best_arm, sampled_probs


def get_posterior_means(context_key: str, db: Session) -> dict[str, float]:
    """
    Return the posterior mean (alpha / (alpha + beta)) for every arm in
    this context.  Used by the knapsack scheduler for stable EV ranking.
    """
    rows = db.execute(
        text("SELECT arm, alpha, beta FROM bandit_posteriors WHERE context_key = :ctx"),
        {"ctx": context_key},
    ).fetchall()
    return {
        row.arm: row.alpha / (row.alpha + row.beta)
        for row in rows
    }


def update_posterior(context_key: str, arm: str, success: bool, db: Session) -> None:
    """
    Bayesian update: increment alpha on success, beta on failure.
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
