# Failure diagnosis

Nummus now diagnoses a payment failure deterministically before it builds the
bandit context. It uses exact normalized identifiers only; it does not inspect
free-text descriptions or call an LLM.

## Categories

The engine returns one of:

- `CARD_DECLINED`
- `INSUFFICIENT_FUNDS`
- `EXPIRED_CARD`
- `NETWORK_ERROR`
- `AUTHENTICATION_FAILURE`
- `BANK_TIMEOUT`
- `UNKNOWN`

For Razorpay, the classifier checks `error_reason` first, then the known
`error_step` and `error_source` values, then recognized `error_code` values,
and finally a legacy ISO-style `decline_code`. The detailed
`error_reason` is preferred because Razorpay documents generic values such as
`BAD_REQUEST_ERROR` alongside a more specific reason like `incorrect_otp`.
Unknown or broad codes remain `UNKNOWN` unless another supported identifier
matches.

The webhook and mock-webhook responses include the diagnosis, which is also
stored in the normalized `webhook_events.payload_json`. Synthetic batches add
the diagnosis category as a fifth context feature. The existing root-cause
bucket stays as the first context field so the legacy simulator and its
ground-truth outcome table continue to work.

The mappings live in `backend/engine/diagnosis.py`. Add codes only when their
meaning is clear from the provider's documented error fields; avoid deriving a
category from a free-text description.

Razorpay references:

- [Payment errors and reasons](https://razorpay.com/docs/errors/payments/list/)
- [Payment entity error fields](https://razorpay.com/docs/api/payments/entity/)
