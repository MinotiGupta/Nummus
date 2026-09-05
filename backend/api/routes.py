"""
routes.py — Phase 6: Complete FastAPI API Layer

All endpoints consumed by the React dashboard and any external tooling.

Endpoint catalogue:
  GET  /health                          — liveness probe
  POST /run-batch?n_events=200          — trigger a full pipeline cycle
  GET  /batch-runs                      — list batch run summaries (newest first)
  GET  /batch-runs/{cycle_id}           — single batch run detail
  GET  /batch-runs/{cycle_id}/audit     — aggregate audit counts for a cycle
  GET  /events?batch_id=&outcome=&limit= — joined event + decision rows
  GET  /decisions?limit=&cycle_id=      — flat decision list with parsed JSON
  GET  /decisions/{decision_id}         — single decision (full detail)
  GET  /bandit/contexts                 — known context keys + human labels
  GET  /bandit/posteriors?context_key=  — raw posteriors grouped by context
  GET  /bandit/stats/{context_key}      — rich per-arm stats for convergence view
"""

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


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    """Liveness probe used by Railway and load balancers."""
    return {"status": "ok"}


# ─── Batch runs ───────────────────────────────────────────────────────────────

@router.post("/run-batch")
def run_batch(n_events: int = Query(200, ge=10, le=1000), db: Session = Depends(get_db)):
    """
    Trigger one complete pipeline cycle (data generation → bandit → scheduler
    → executor → audit write).

    Returns the full batch summary including knapsack stats.
    """
    result = run_batch_cycle(db, n_events)
    return result


@router.get("/batch-runs")
def get_batch_runs(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """
    List the most recent batch runs, newest first.
    Includes all summary metrics needed by BatchSummary.jsx.
    """
    rows = db.execute(
        text("SELECT * FROM batch_runs ORDER BY run_at DESC LIMIT :lim"),
        {"lim": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/batch-runs/{cycle_id}/audit")
def get_cycle_audit(cycle_id: str, db: Session = Depends(get_db)):
    """
    Aggregate decision-level audit counts for a specific batch cycle.
    Used by the AuditTrail component to show arm distribution and stop-rule stats.
    """
    # Verify the cycle exists
    exists = db.execute(
        text("SELECT cycle_id FROM batch_runs WHERE cycle_id = :cid"),
        {"cid": cycle_id},
    ).first()
    if not exists:
        raise HTTPException(404, f"Cycle {cycle_id} not found")
    return get_cycle_audit_summary(cycle_id, db)


@router.get("/batch-runs/{cycle_id}")
def get_batch_run(cycle_id: str, db: Session = Depends(get_db)):
    """Single batch run detail row."""
    row = db.execute(
        text("SELECT * FROM batch_runs WHERE cycle_id = :cid"),
        {"cid": cycle_id},
    ).mappings().first()
    if not row:
        raise HTTPException(404, f"Cycle {cycle_id} not found")
    return dict(row)


# ─── Events ───────────────────────────────────────────────────────────────────

@router.get("/events")
def get_events(
    batch_id: str  = Query(None),
    outcome:  str  = Query(None, description="recovered | lost | deferred | held"),
    limit:    int  = Query(200, ge=1, le=1000),
    db: Session    = Depends(get_db),
):
    """
    Return events joined with their decision records.
    Supports filtering by batch_id and outcome label.
    """
    query = """
        SELECT
            e.event_id, e.account_id, e.amount, e.currency,
            e.decline_code, e.timestamp, e.root_cause, e.retryable, e.batch_id,
            d.decision_id, d.chosen_arm, d.predicted_ev,
            d.budget_selected, d.actual_outcome, d.stopping_rule_reason,
            d.context_key, d.created_at as decision_at
        FROM events e
        LEFT JOIN decisions d ON e.event_id = d.event_id
        WHERE 1=1
    """
    params: dict = {}

    if batch_id:
        query += " AND e.batch_id = :bid"
        params["bid"] = batch_id

    query += " ORDER BY e.timestamp DESC LIMIT :lim"
    params["lim"] = limit

    rows = db.execute(text(query), params).mappings().all()
    result = []
    for r in rows:
        d = dict(r)
        # Compute outcome label for client convenience
        if d.get("budget_selected") == 0:
            d["outcome_label"] = "deferred"
        elif d.get("chosen_arm") == "hold_no_action":
            d["outcome_label"] = "held"
        elif d.get("actual_outcome") == 1:
            d["outcome_label"] = "recovered"
        else:
            d["outcome_label"] = "lost"

        # Apply outcome filter
        if outcome and d["outcome_label"] != outcome:
            continue

        result.append(d)

    return result


# ─── Decisions ────────────────────────────────────────────────────────────────

def _parse_decision(d: dict) -> dict:
    """Parse JSON string fields in a decision row."""
    d["candidate_arms"] = (
        json.loads(d["candidate_arms"]) if d.get("candidate_arms") else []
    )
    d["sampled_probabilities"] = (
        json.loads(d["sampled_probabilities"]) if d.get("sampled_probabilities") else {}
    )
    # Add human-readable context label
    if d.get("context_key"):
        d["context_label"] = context_label(d["context_key"])
        d["context_decoded"] = decode_context(d["context_key"])
    return d


@router.get("/decisions")
def get_all_decisions(
    limit:    int  = Query(100, ge=1, le=500),
    cycle_id: str  = Query(None),
    db: Session    = Depends(get_db),
):
    """
    Return the most recent decisions with JSON fields parsed.
    Optionally filter by cycle_id.
    """
    query = "SELECT * FROM decisions WHERE 1=1"
    params: dict = {"lim": limit}

    if cycle_id:
        query += " AND cycle_id = :cid"
        params["cid"] = cycle_id

    query += " ORDER BY created_at DESC LIMIT :lim"
    rows = db.execute(text(query), params).mappings().all()
    return [_parse_decision(dict(r)) for r in rows]


@router.get("/decisions/{decision_id}")
def get_decision(decision_id: str, db: Session = Depends(get_db)):
    """Full decision detail including parsed candidate_arms and sampled_probabilities."""
    row = db.execute(
        text("SELECT * FROM decisions WHERE decision_id = :id"),
        {"id": decision_id},
    ).mappings().first()
    if not row:
        raise HTTPException(404, f"Decision {decision_id} not found")
    return _parse_decision(dict(row))


# ─── Bandit ───────────────────────────────────────────────────────────────────

@router.get("/bandit/contexts")
def get_bandit_contexts(db: Session = Depends(get_db)):
    """
    Return all known context keys with human-readable labels.
    Used to populate the convergence view context dropdown.
    """
    rows = db.execute(
        text("SELECT DISTINCT context_key FROM bandit_posteriors ORDER BY context_key")
    ).fetchall()
    return [
        {
            "context_key": r.context_key,
            "label":       context_label(r.context_key),
            "decoded":     decode_context(r.context_key),
        }
        for r in rows
    ]


@router.get("/bandit/posteriors")
def get_posteriors(context_key: str = Query(None), db: Session = Depends(get_db)):
    """Raw posterior rows grouped by context_key. Legacy endpoint kept for compatibility."""
    query  = "SELECT * FROM bandit_posteriors"
    params: dict = {}
    if context_key:
        query += " WHERE context_key = :ctx"
        params["ctx"] = context_key

    rows = db.execute(text(query), params).mappings().all()
    grouped: dict = {}
    for r in rows:
        ctx = r["context_key"]
        grouped.setdefault(ctx, []).append(dict(r))
    return grouped


@router.get("/bandit/stats/{context_key:path}")
def get_stats(context_key: str, db: Session = Depends(get_db)):
    """
    Rich per-arm statistics for one context key.
    Includes posterior_mean, n_trials, and 90% credible interval.
    Powers the convergence bar chart.
    """
    stats = get_bandit_stats(context_key, db)
    if not stats:
        raise HTTPException(404, f"No bandit data for context: {context_key}")
    return {
        "context_key": context_key,
        "label":       context_label(context_key),
        "decoded":     decode_context(context_key),
        "arms":        stats,
    }
