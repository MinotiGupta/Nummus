import os
from db.schema import init_db
from db.connection import SessionLocal
from engine.batch_runner import run_batch_cycle

DB_PATH = "data/razorpay.db"

if __name__ == "__main__":
    print("Preparing clean database for demo...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Removed old database.")
    
    init_db()
    print("Initialized fresh schema.")
    
    db = SessionLocal()
    print("Running 5 initial batches to pre-warm the Contextual Bandit...")
    for i in range(1, 6):
        print(f"  Running batch {i}/5...")
        result = run_batch_cycle(db, n_events=200)
        eff = result['efficiency']
        rec = result['recovery_rate']
        base = result['baseline_rate']
        print(f"    -> Agent {rec}% | Baseline {base}% | Efficiency: {eff:+.1f}pp")
    
    db.close()
    print("\nPre-seeding complete! The dashboard is ready for the demo.")
