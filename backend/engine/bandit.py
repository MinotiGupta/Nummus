import datetime
import scipy.stats
from sqlalchemy.orm import Session
from sqlalchemy import text
from db.schema import bandit_posteriors

ARMS = [
    "retry_immediate", 
    "retry_delayed_2h", 
    "retry_delayed_24h",
    "offer_alt_payment_method", 
    "send_reminder_email",
    "send_reminder_sms", 
    "escalate_human_call", 
    "hold_no_action"
]

def get_posteriors(context_key: str, eligible_arms: list, db: Session):
    # Fetch posteriors from DB
    result = db.execute(text(
        "SELECT arm, alpha, beta FROM bandit_posteriors WHERE context_key = :context_key"
    ), {"context_key": context_key}).fetchall()
    
    posteriors = {row.arm: {"alpha": row.alpha, "beta": row.beta} for row in result}
    
    # Fill in defaults if not present
    new_arms = []
    for arm in eligible_arms:
        if arm not in posteriors:
            posteriors[arm] = {"alpha": 1.0, "beta": 1.0}
            new_arms.append({
                "context_key": context_key,
                "arm": arm,
                "alpha": 1.0,
                "beta": 1.0,
                "updated_at": datetime.datetime.utcnow().isoformat()
            })
            
    if new_arms:
        db.execute(
            text("""
            INSERT INTO bandit_posteriors (context_key, arm, alpha, beta, updated_at) 
            VALUES (:context_key, :arm, :alpha, :beta, :updated_at)
            """), 
            new_arms
        )
        db.commit()
        
    return posteriors

def select_action(context_key: str, eligible_arms: list, db: Session):
    if not eligible_arms:
        return None, {}
        
    posteriors = get_posteriors(context_key, eligible_arms, db)
    
    best_arm = None
    best_sample = -1.0
    sampled_probs = {}
    
    for arm in eligible_arms:
        alpha = posteriors[arm]["alpha"]
        beta = posteriors[arm]["beta"]
        # Thompson sample
        sample = scipy.stats.beta.rvs(alpha, beta)
        sampled_probs[arm] = float(sample)
        
        if sample > best_sample:
            best_sample = sample
            best_arm = arm
            
    return best_arm, sampled_probs

def update_posterior(context_key: str, arm: str, success: bool, db: Session):
    db.execute(text("""
        UPDATE bandit_posteriors 
        SET alpha = alpha + :d_alpha, 
            beta = beta + :d_beta, 
            updated_at = :updated_at 
        WHERE context_key = :context_key AND arm = :arm
    """), {
        "d_alpha": 1.0 if success else 0.0,
        "d_beta": 0.0 if success else 1.0,
        "updated_at": datetime.datetime.utcnow().isoformat(),
        "context_key": context_key,
        "arm": arm
    })
    db.commit()
