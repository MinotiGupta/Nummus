"""Normalize and persist inbound failed-payment webhook events."""

import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session


def normalize_event_timestamp(value: object) -> str:
    """Convert a Razorpay Unix timestamp or ISO timestamp to UTC ISO format."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    raise ValueError("event timestamp is missing or invalid")


def persist_payment_failed(
    db: Session,
    *,
    event_id: str,
    source: str,
    event_name: str,
    payment_id: str,
    order_id: str | None,
    customer_id: str | None,
    amount_minor: int,
    currency: str,
    method: str | None,
    error_code: str | None,
    event_timestamp: object,
    safe_payload: dict,
) -> bool:
    """Persist a normalized event once. Return False for a duplicate ID."""
    now = datetime.now(timezone.utc).isoformat()
    result = db.execute(
        text("""
            INSERT INTO webhook_events (
                event_id, source, event_name, payment_id, order_id, customer_id,
                amount_minor, currency, method, error_code, event_timestamp,
                received_at, payload_json, processing_status
            ) VALUES (
                :event_id, :source, :event_name, :payment_id, :order_id,
                :customer_id, :amount_minor, :currency, :method, :error_code,
                :event_timestamp, :received_at, :payload_json, 'received'
            ) ON CONFLICT(event_id) DO NOTHING
        """),
        {
            "event_id": event_id,
            "source": source,
            "event_name": event_name,
            "payment_id": payment_id,
            "order_id": order_id,
            "customer_id": customer_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "method": method,
            "error_code": error_code,
            "event_timestamp": normalize_event_timestamp(event_timestamp),
            "received_at": now,
            # Persist only normalized fields. Razorpay's full payment snapshot
            # can contain card and customer details that this layer does not need.
            "payload_json": json.dumps(safe_payload, separators=(",", ":")),
        },
    )
    db.commit()
    return result.rowcount == 1
