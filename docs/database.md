# Nummus state database

The backend creates the state tables during startup with `CREATE TABLE IF NOT
EXISTS`. Existing event, webhook, bandit, and decision tables remain in place.
PostgreSQL is selected through `DATABASE_URL`; SQLite remains the local fallback
for the legacy demo.

## Configure PostgreSQL

Install backend requirements, including the Psycopg 3 PostgreSQL driver, then
set a SQLAlchemy connection URL before starting FastAPI:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://nummus:password@localhost:5432/nummus"
cd backend
uvicorn main:app --reload
```

The backend also normalizes provider URLs beginning with `postgres://` or
`postgresql://` to the Psycopg 3 SQLAlchemy dialect. Keep credentials in the
deployment environment; do not commit them.

## Core state

- `customers` stores customer segments and aggregate payment history.
- `payments` stores payment facts; `amount` is in major currency units (for
  example, rupees). Razorpay webhook amounts arrive in minor units and must be
  converted before a payment row is created.
- `recovery_attempts` stores each planned or executed action, its status, and
  cost.
- `recovery_outcomes` stores the eventual result for an attempt.
- `policies` stores action limits. Cooldowns are represented as
  `cooldown_seconds`; costs use major currency units.
- `audit_logs` records event, decision, actor, reason, and optional links to a
  payment or attempt.

`time_to_recovery_seconds` is an integer duration in seconds. The webhook
ingestion endpoint currently writes to `webhook_events`; connecting those
events to `customers` and `payments` is a later workflow step. This schema
creation does not itself populate customer records or trigger recovery actions.
