import re
from copy import copy
from typing import Any


KNOWN_CUSTOMER_NAMES = (
    "Budi Santoso",
    "Siti Aminah",
    "Andi Wijaya",
    "Rina Kartika",
    "Doni Pratama",
    "Lina Susanti",
    "Hendra Gunawan",
    "Maya Putri",
)

PII_INVENTORY = {
    "name": "Customer names stored on users/orders/support records.",
    "email": "Customer emails used for login/session identity and order ownership.",
    "phone": "Customer phone numbers stored on user profiles when present.",
    "address": "Shipping and default address fields.",
    "customer_ids": "User UUIDs, external IDs, session IDs, and prompt-supplied customer_id values.",
    "payment_related_metadata": "Payment references, payment method metadata, and transaction-like identifiers.",
}

REDACTION_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\+?62|0)\d[\d\s-]{7,}\d\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE), "[REDACTED_CUSTOMER_ID]"),
    (re.compile(r"\b(customer_id|user_id|external_id|session_id)\s*[:=]\s*[A-Za-z0-9_.:-]+", re.IGNORECASE), r"\1=[REDACTED_CUSTOMER_ID]"),
    (re.compile(r"(Customer:\s*)[^\n\r]+", re.IGNORECASE), r"\1[REDACTED_NAME]"),
    (re.compile(r"(customer\s+')[^']+(')", re.IGNORECASE), r"\1[REDACTED_NAME]\2"),
    (re.compile(r"(Address:\s*)[^\n\r]+", re.IGNORECASE), r"\1[REDACTED_ADDRESS]"),
    (re.compile(r"(Old address:\s*)[^\n\r]+", re.IGNORECASE), r"\1[REDACTED_ADDRESS]"),
    (re.compile(r"(New address:\s*)[^\n\r]+", re.IGNORECASE), r"\1[REDACTED_ADDRESS]"),
    (re.compile(r"\bJl\.\s*[^,\n\r]+(?:,\s*[^\n\r]+)?", re.IGNORECASE), "[REDACTED_ADDRESS]"),
    (re.compile(r"\b(?:" + "|".join(re.escape(name) for name in KNOWN_CUSTOMER_NAMES) + r")\b", re.IGNORECASE), "[REDACTED_NAME]"),
    (re.compile(r"\b(payment_reference|transaction_id|card_last4|bank_account)\s*[:=]\s*[A-Za-z0-9_.:-]+", re.IGNORECASE), r"\1=[REDACTED_PAYMENT_METADATA]"),
]

PII_DETECTION_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?62|0)\d[\d\s-]{7,}\d\b"),
    "customer_ids": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),
    "identity_keys": re.compile(r"\b(customer_id|user_id|external_id|session_id)\s*[:=]\s*(?!\[REDACTED_CUSTOMER_ID\])[A-Za-z0-9_.:-]+", re.IGNORECASE),
    "address": re.compile(r"\bJl\.\s*[^,\n\r]+(?:,\s*[^\n\r]+)?", re.IGNORECASE),
    "name": re.compile(r"\b(?:" + "|".join(re.escape(name) for name in KNOWN_CUSTOMER_NAMES) + r")\b", re.IGNORECASE),
    "payment_related_metadata": re.compile(r"\b(payment_reference|transaction_id|card_last4|bank_account)\s*[:=]\s*(?!\[REDACTED_PAYMENT_METADATA\])[A-Za-z0-9_.:-]+", re.IGNORECASE),
}


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_for_llm(value: Any) -> Any:
    return _redact_value(value)


def redact_for_logs(value: Any) -> Any:
    return _redact_value(value)


def detect_pii(value: Any) -> dict[str, list[str]]:
    text = _stringify(value)
    findings: dict[str, list[str]] = {}
    for label, pattern in PII_DETECTION_PATTERNS.items():
        matches = sorted({match.group(0) for match in pattern.finditer(text)})
        if matches:
            findings[label] = matches
    return findings


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(f"{key}: {_stringify(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return " ".join(_stringify(item) for item in value)
    return "" if value is None else str(value)


def redact_message_content(message: Any) -> Any:
    content = getattr(message, "content", None)
    if not isinstance(content, str):
        return message
    redacted = copy(message)
    redacted.content = redact_text(content)
    return redacted
