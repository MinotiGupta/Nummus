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

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from db.connection import get_db
from engine.batch_runner import run_batch_cycle
from engine.bandit import get_bandit_stats
from engine.context_builder import decode_context, context_label
from engine.executor import get_cycle_audit_summary
from engine.event_ingestion import normalize_event_timestamp, persist_payment_failed
from engine.diagnosis import diagnose_failure

router = APIRouter()


class MockFailedPayment(BaseModel):
    """Development event shape; amount is expressed in major currency units."""

    event_id: str | None = None
    event: Literal["payment.failed"] = "payment.failed"
    payment_id: str = Field(min_length=1)
    order_id: str | None = None
    customer_id: str | None = None
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    method: str | None = None
    error_code: str | None = None
    error_reason: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    decline_code: str | None = None
    timestamp: datetime


def _store_razorpay_payload(db: Session, event_id: str, payload: dict, source: str):
    if payload.get("event") != "payment.failed":
        raise HTTPException(status_code=422, detail="Only payment.failed events are accepted")
    webhook_data = payload.get("payload")
    payment_data = webhook_data.get("payment") if isinstance(webhook_data, dict) else None
    payment = payment_data.get("entity") if isinstance(payment_data, dict) else None
    if not isinstance(payment, dict):
        raise HTTPException(status_code=422, detail="Missing payload.payment.entity")
    try:
        payment_id = payment["id"]
        amount_minor = payment["amount"]
        currency = payment["currency"]
        event_timestamp = payload.get("created_at", payment.get("created_at"))
        if not isinstance(payment_id, str) or not payment_id:
            raise ValueError("payment id is invalid")
        if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor < 0:
            raise ValueError("payment amount must be a non-negative integer in subunits")
        if not isinstance(currency, str) or len(currency) != 3:
            raise ValueError("payment currency is invalid")
        if event_timestamp is None:
            raise ValueError("event timestamp is missing")
        normalized_timestamp = normalize_event_timestamp(event_timestamp)
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    normalized = {
        "event": "payment.failed",
        "payment_id": payment_id,
        "order_id": payment.get("order_id"),
        "customer_id": payment.get("customer_id"),
        "amount_minor": amount_minor,
        "currency": currency,
        "method": payment.get("method"),
        "error_code": payment.get("error_code"),
        "error_reason": payment.get("error_reason"),
        "error_source": payment.get("error_source"),
        "error_step": payment.get("error_step"),
        "timestamp": normalized_timestamp,
    }
    diagnosis = diagnose_failure(normalized).to_dict()
    normalized["diagnosis"] = diagnosis
    inserted = persist_payment_failed(
        db,
        event_id=event_id,
        source=source,
        event_name="payment.failed",
        payment_id=payment_id,
        order_id=payment.get("order_id"),
        customer_id=payment.get("customer_id"),
        amount_minor=amount_minor,
        currency=currency,
        method=payment.get("method"),
        error_code=payment.get("error_code"),
        event_timestamp=normalized_timestamp,
        safe_payload=normalized,
    )
    return {
        "received": True,
        "duplicate": not inserted,
        "event_id": event_id,
        "diagnosis": diagnosis,
    }


@router.post("/webhooks/razorpay")
async def receive_razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Verify and store a Razorpay payment.failed webhook, without processing it."""
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook secret is not configured")

    raw_body = await request.body()
    supplied_signature = request.headers.get("x-razorpay-signature", "")
    expected_signature = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not supplied_signature or not hmac.compare_digest(expected_signature, supplied_signature):
        raise HTTPException(status_code=401, detail="Invalid Razorpay webhook signature")

    event_id = request.headers.get("x-razorpay-event-id")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing X-Razorpay-Event-Id header")
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook body must be a JSON object")
    return _store_razorpay_payload(db, event_id, payload, "razorpay")


@router.post("/mock-webhook")
def inject_mock_webhook(event: MockFailedPayment, db: Session = Depends(get_db)):
    """Inject a normalized development event when explicitly enabled."""
    enabled = os.environ.get("ENABLE_MOCK_WEBHOOK", "false").lower() == "true"
    app_env = os.environ.get("APP_ENV", "production").lower()
    if not enabled or app_env not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        amount_minor = int((event.amount * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="amount must have at most two decimal places") from exc
    if Decimal(amount_minor) / 100 != event.amount:
        raise HTTPException(status_code=422, detail="amount must have at most two decimal places")

    event_id = event.event_id or f"mock_{uuid.uuid4()}"
    payload = {
        "event": event.event,
        "payment_id": event.payment_id,
        "order_id": event.order_id,
        "customer_id": event.customer_id,
        "amount_minor": amount_minor,
        "currency": event.currency.upper(),
        "method": event.method,
        "error_code": event.error_code,
        "error_reason": event.error_reason,
        "error_source": event.error_source,
        "error_step": event.error_step,
        "decline_code": event.decline_code,
        "timestamp": event.timestamp.isoformat(),
    }
    diagnosis = diagnose_failure(payload).to_dict()
    payload["diagnosis"] = diagnosis
    inserted = persist_payment_failed(
        db,
        event_id=event_id,
        source="mock",
        event_name=event.event,
        payment_id=event.payment_id,
        order_id=event.order_id,
        customer_id=event.customer_id,
        amount_minor=amount_minor,
        currency=event.currency.upper(),
        method=event.method,
        error_code=event.error_code,
        event_timestamp=event.timestamp.isoformat(),
        safe_payload=payload,
    )
    return {
        "received": True,
        "duplicate": not inserted,
        "event_id": event_id,
        "diagnosis": diagnosis,
    }


@router.get("/webhook-events/{event_id}")
def get_webhook_event(event_id: str, db: Session = Depends(get_db)):
    """Read an ingested event to make the event-layer demo inspectable."""
    row = db.execute(
        text("SELECT * FROM webhook_events WHERE event_id = :event_id"),
        {"event_id": event_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Webhook event not found")
    result = dict(row)
    result["payload"] = json.loads(result.pop("payload_json"))
    return result


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
