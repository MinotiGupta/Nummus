# Payment event ingestion

This phase stores failed-payment events. It does not invoke the bandit or take
recovery actions.

## Local mock event

Start the backend with these environment variables set:

```powershell
$env:APP_ENV = "development"
$env:ENABLE_MOCK_WEBHOOK = "true"
cd backend
uvicorn main:app --reload
```

Inject an event. The mock endpoint takes `amount` in major currency units
(rupees for INR); it converts that value to minor units in storage.

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/mock-webhook `
  -ContentType "application/json" `
  -Body '{"event":"payment.failed","payment_id":"pay_mock_123","order_id":"order_123","customer_id":"cust_456","amount":2499,"currency":"INR","method":"card","error_code":"BAD_REQUEST_ERROR","error_reason":"insufficient_funds","timestamp":"2026-09-24T12:30:00Z"}'
```

The response includes an `event_id`. Read the persisted row with:

```powershell
Invoke-RestMethod http://localhost:8000/api/webhook-events/EVENT_ID_FROM_RESPONSE
```

Replace `EVENT_ID_FROM_RESPONSE` with the value returned by the mock endpoint.

To test deduplication, supply an explicit `event_id` in the mock request and
send it twice. The second response has `duplicate: true`.

## Razorpay webhook

Configure the public endpoint URL as `POST /api/webhooks/razorpay` and set
`RAZORPAY_WEBHOOK_SECRET` to the webhook secret from Razorpay Dashboard. This
endpoint verifies `X-Razorpay-Signature` against the unmodified raw request
body, then deduplicates on `x-razorpay-event-id`. It currently accepts only
`payment.failed` and extracts the payment entity from
`payload.payment.entity`. Razorpay payment `amount` values are stored as
integer minor currency units (for INR, paise).

Only the normalized event fields are persisted; card data and other fields in
the full payment snapshot are intentionally not copied into the database.
Invalid signatures are rejected, missing event IDs are rejected, and duplicate
delivery is acknowledged without creating a second row.

## Current boundary

Events are inserted into the separate `webhook_events` table with
`processing_status = received`. They are not yet transformed into legacy
synthetic `events` rows or sent through Nummus's recovery pipeline. The mock
route is disabled by default and returns 404 unless `APP_ENV` is `development`
or `test` and `ENABLE_MOCK_WEBHOOK=true`.

Razorpay references:

- [Validate and test webhooks](https://razorpay.com/docs/webhooks/validate-test/)
- [Payment entity fields](https://razorpay.com/docs/api/payments/entity/)
- [Payment failed webhook sample](https://razorpay.com/docs/payments/subscriptions/plugins/woocommerce/webhook-events/)
