from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from db.connection import get_db
from engine.batch_runner import run_batch_cycle
from engine.bandit import get_bandit_stats
from engine.context_builder import decode_context, context_label
from engine.executor import get_cycle_audit_summary
import json

router = APIRouter()

@router.post("/run-batch")
def run_batch(n_events: int = 200, db: Session = Depends(get_db)):
    result = run_batch_cycle(db, n_events)
    return result

@router.get("/batch-runs")
def get_batch_runs(db: Session = Depends(get_db)):
    runs = db.execute(text("SELECT * FROM batch_runs ORDER BY run_at DESC LIMIT 50")).mappings().all()
    return list(runs)

@router.get("/batch-runs/{cycle_id}")
def get_batch_run(cycle_id: str, db: Session = Depends(get_db)):
    run = db.execute(text("SELECT * FROM batch_runs WHERE cycle_id = :cid"), {"cid": cycle_id}).mappings().first()
    if not run:
        raise HTTPException(404, "Not found")
    return dict(run)

@router.get("/events")
def get_events(batch_id: str = None, outcome: str = None, db: Session = Depends(get_db)):
    query = """
        SELECT e.*, d.actual_outcome, d.chosen_arm, d.predicted_ev, d.budget_selected, d.decision_id
        FROM events e
        LEFT JOIN decisions d ON e.event_id = d.event_id
        WHERE 1=1
    """
    params = {}
    if batch_id:
        query += " AND e.batch_id = :bid"
        params["bid"] = batch_id
        
    events = db.execute(text(query), params).mappings().all()
    
    # Filter in python for simplicity if needed
    result = []
    for e in events:
        d = dict(e)
        if outcome:
            if outcome == "deferred" and d.get("budget_selected") == 0:
                pass
            elif outcome == "recovered" and d.get("actual_outcome") == 1:
                pass
            elif outcome == "lost" and d.get("actual_outcome") == 0 and d.get("budget_selected") == 1:
                pass
            else:
                continue
        result.append(d)
        
    return result

@router.get("/decisions/{decision_id}")
def get_decision(decision_id: str, db: Session = Depends(get_db)):
    d = db.execute(text("SELECT * FROM decisions WHERE decision_id = :id"), {"id": decision_id}).mappings().first()
    if not d:
        raise HTTPException(404, "Not found")
        
    d = dict(d)
    d["candidate_arms"] = json.loads(d["candidate_arms"]) if d.get("candidate_arms") else []
    d["sampled_probabilities"] = json.loads(d["sampled_probabilities"]) if d.get("sampled_probabilities") else {}
    return d

@router.get("/decisions")
def get_all_decisions(limit: int = Query(100), db: Session = Depends(get_db)):
    d = db.execute(text("SELECT * FROM decisions ORDER BY created_at DESC LIMIT :limit"), {"limit": limit}).mappings().all()
    return list(d)

@router.get("/bandit/posteriors")
def get_posteriors(context_key: str = None, db: Session = Depends(get_db)):
    query = "SELECT * FROM bandit_posteriors"
    params = {}
    if context_key:
        query += " WHERE context_key = :ctx"
        params["ctx"] = context_key
        
    res = db.execute(text(query), params).mappings().all()
    
    # Group by context_key
    grouped = {}
    for r in res:
        ctx = r["context_key"]
        if ctx not in grouped:
            grouped[ctx] = []
        grouped[ctx].append(dict(r))
        
    return grouped


@router.get("/bandit/contexts")
def get_bandit_contexts(db: Session = Depends(get_db)):
    """
    Return all known context keys with their human-readable labels.
    Used to populate the convergence view dropdown.
    """
    rows = db.execute(
        text("SELECT DISTINCT context_key FROM bandit_posteriors ORDER BY context_key")
    ).fetchall()
    return [
        {
            "context_key": row.context_key,
            "label":       context_label(row.context_key),
            "decoded":     decode_context(row.context_key),
        }
        for row in rows
    ]


@router.get("/bandit/stats/{context_key:path}")
def get_stats(context_key: str, db: Session = Depends(get_db)):
    """
    Return rich per-arm statistics for a context, including posterior mean,
    trial count, and 90% credible interval bands.
    Powers the convergence view bar chart.
    """
    stats = get_bandit_stats(context_key, db)
    if not stats:
        raise HTTPException(404, f"No data for context: {context_key}")
    return {
        "context_key": context_key,
        "label":       context_label(context_key),
        "decoded":     decode_context(context_key),
        "arms":        stats,
    }
