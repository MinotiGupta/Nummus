import os
from sqlalchemy import text
from .connection import engine

def init_db():
    # Ensure data directory exists if using sqlite
    if str(engine.url).startswith("sqlite"):
        db_path = str(engine.url).replace("sqlite:///", "")
        if not db_path.startswith(":memory:"):
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

    with engine.connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS events (
            event_id        TEXT PRIMARY KEY,
            account_id      TEXT NOT NULL,
            event_type      TEXT DEFAULT 'payment_failure',
            amount          REAL NOT NULL,
            currency        TEXT DEFAULT 'INR',
            decline_code    TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            root_cause      TEXT,
            retryable       INTEGER,
            batch_id        TEXT
        );
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id          TEXT PRIMARY KEY,
            contact_count       INTEGER DEFAULT 0,
            first_failure_at    TEXT,
            last_action_at      TEXT,
            self_resolve_score  REAL DEFAULT 0.3,
            status              TEXT DEFAULT 'active'
        );
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS bandit_posteriors (
            context_key TEXT NOT NULL,
            arm         TEXT NOT NULL,
            alpha       REAL DEFAULT 1.0,
            beta        REAL DEFAULT 1.0,
            updated_at  TEXT,
            PRIMARY KEY (context_key, arm)
        );
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id             TEXT PRIMARY KEY,
            event_id                TEXT NOT NULL,
            cycle_id                TEXT NOT NULL,
            context_key             TEXT NOT NULL,
            candidate_arms          TEXT,
            sampled_probabilities   TEXT,
            chosen_arm              TEXT,
            predicted_ev            REAL,
            budget_selected         INTEGER,
            stopping_rule_reason    TEXT,
            actual_outcome          INTEGER,
            amount_recovered        REAL DEFAULT 0,
            created_at              TEXT
        );
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS batch_runs (
            cycle_id                    TEXT PRIMARY KEY,
            run_at                      TEXT,
            total_events                INTEGER,
            total_at_risk_amount        REAL,
            total_recovered_amount      REAL,
            baseline_recovered_amount   REAL,
            recovery_rate               REAL,
            efficiency_vs_baseline      REAL
        );
        """))
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
