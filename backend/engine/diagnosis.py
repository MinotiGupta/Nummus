"""Deterministic payment-failure diagnosis from provider error identifiers.

This module deliberately uses exact normalized code mappings. It does not infer
causes from free-text descriptions and does not call an LLM.
"""

import re
from dataclasses import asdict, dataclass
from typing import Mapping


CARD_DECLINED = "CARD_DECLINED"
INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
EXPIRED_CARD = "EXPIRED_CARD"
NETWORK_ERROR = "NETWORK_ERROR"
AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
BANK_TIMEOUT = "BANK_TIMEOUT"
UNKNOWN = "UNKNOWN"


# Razorpay's error_reason values are more specific than error_code values.
# Generic codes such as BAD_REQUEST_ERROR are intentionally not mapped.
ERROR_REASON_CATEGORIES = {
    "insufficient_funds": INSUFFICIENT_FUNDS,
    "card_expired": EXPIRED_CARD,
    "incorrect_card_expiry_date": EXPIRED_CARD,
    "authentication_failed": AUTHENTICATION_FAILURE,
    "incorrect_otp": AUTHENTICATION_FAILURE,
    "otp_expired": AUTHENTICATION_FAILURE,
    "otp_attempts_exceeded": AUTHENTICATION_FAILURE,
    "incorrect_pin": AUTHENTICATION_FAILURE,
    "incorrect_atm_pin": AUTHENTICATION_FAILURE,
    "pin_attempts_exceeded": AUTHENTICATION_FAILURE,
    "incorrect_cvv": AUTHENTICATION_FAILURE,
    "payment_cancelled": AUTHENTICATION_FAILURE,
    "card_declined": CARD_DECLINED,
    "debit_declined": CARD_DECLINED,
    "payment_declined": CARD_DECLINED,
    "debit_instrument_blocked": CARD_DECLINED,
    "card_number_invalid": CARD_DECLINED,
    "card_type_invalid": CARD_DECLINED,
    "incorrect_card_details": CARD_DECLINED,
    "bank_cutoff_in_progress": BANK_TIMEOUT,
    "payment_timed_out": BANK_TIMEOUT,
    "request_timed_out": BANK_TIMEOUT,
    "mandate_creation_timeout": BANK_TIMEOUT,
    "bank_technical_error": NETWORK_ERROR,
    "bank_not_available": NETWORK_ERROR,
    "gateway_technical_error": NETWORK_ERROR,
    "issuer_technical_error": NETWORK_ERROR,
    "invalid_response_from_gateway": NETWORK_ERROR,
    "payment_failed": NETWORK_ERROR,
    "payment_declined_due_to_high_traffic": NETWORK_ERROR,
    "server_error": NETWORK_ERROR,
    "verification_failed": NETWORK_ERROR,
    "upi_app_technical_error": NETWORK_ERROR,
    "psp_app_not_available": NETWORK_ERROR,
    "psp_not_available": NETWORK_ERROR,
    "vpa_resolution_failed": NETWORK_ERROR,
}

# Coarse Razorpay error_code values. Exact granular `error_reason` takes
# precedence over these when both are present.
ERROR_CODE_CATEGORIES = {
    "gateway_error": NETWORK_ERROR,
    "server_error": NETWORK_ERROR,
    "card_declined": CARD_DECLINED,
    "insufficient_funds": INSUFFICIENT_FUNDS,
    "expired_card": EXPIRED_CARD,
    "network_error": NETWORK_ERROR,
    "authentication_failure": AUTHENTICATION_FAILURE,
    "bank_timeout": BANK_TIMEOUT,
    "unknown": UNKNOWN,
}

ERROR_STEP_CATEGORIES = {
    "payment_authentication": AUTHENTICATION_FAILURE,
}

ERROR_SOURCE_CATEGORIES = {
    "gateway": NETWORK_ERROR,
    "razorpay": NETWORK_ERROR,
}

# Existing synthetic events use ISO-style decline codes. Keep a deterministic
# mapping for that source as well as the Razorpay reason-code mapping above.
DECLINE_CODE_CATEGORIES = {
    "51": INSUFFICIENT_FUNDS,
    "65": INSUFFICIENT_FUNDS,
    "61": CARD_DECLINED,
    "54": EXPIRED_CARD,
    "33": EXPIRED_CARD,
    "41": CARD_DECLINED,
    "43": CARD_DECLINED,
    "05": CARD_DECLINED,
    "12": CARD_DECLINED,
    "57": CARD_DECLINED,
    "59": CARD_DECLINED,
    "62": CARD_DECLINED,
    "93": CARD_DECLINED,
    "96": NETWORK_ERROR,
    "91": NETWORK_ERROR,
    "06": NETWORK_ERROR,
}


@dataclass(frozen=True)
class FailureDiagnosis:
    category: str
    matched_code: str | None
    matched_field: str | None
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_code(value: object) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized or None


def diagnose_failure(
    event: Mapping[str, object] | None = None,
    *,
    error_code: object = None,
    error_reason: object = None,
    decline_code: object = None,
) -> FailureDiagnosis:
    """Return a stable category using exact code lookups only.

    Lookup order is granular Razorpay `error_reason`, recognized provider
    `error_code`, then the legacy ISO-style `decline_code`.
    """
    fields = dict(event or {})
    candidates = (
        ("error_reason", error_reason if error_reason is not None else fields.get("error_reason"), ERROR_REASON_CATEGORIES),
        ("error_step", fields.get("error_step"), ERROR_STEP_CATEGORIES),
        ("error_source", fields.get("error_source"), ERROR_SOURCE_CATEGORIES),
        ("error_code", error_code if error_code is not None else fields.get("error_code"), ERROR_CODE_CATEGORIES),
        ("decline_code", decline_code if decline_code is not None else fields.get("decline_code"), DECLINE_CODE_CATEGORIES),
    )

    first_code = None
    for field, raw_code, mapping in candidates:
        code = _normalize_code(raw_code)
        if code is None:
            continue
        if first_code is None:
            first_code = code
        category = mapping.get(code)
        if category:
            return FailureDiagnosis(
                category=category,
                matched_code=code,
                matched_field=field,
                rationale=f"Mapped exact {field} value '{code}'.",
            )

    return FailureDiagnosis(
        category=UNKNOWN,
        matched_code=first_code,
        matched_field=None,
        rationale="No configured exact code mapping matched; manual review may be needed.",
    )
