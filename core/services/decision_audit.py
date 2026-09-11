"""Execution evidence only: never persist messages containing private reasoning."""
import hashlib
import json

from core.privacy import redact_for_logs

SENSITIVE_KEYS = {
    "password", "secret", "api_key", "authorization", "token", "email", "phone",
    "address", "new_address", "shipping_address", "customer_name", "customer_id",
    "user_id", "session_id", "payment_reference", "bank_account", "name_on_card",
}
PRIVATE_KEYS = {"reasoning", "analysis", "chain_of_thought", "system_prompt", "messages", "prompt_text"}
EVENT_ATTRIBUTES = (
    "provider", "model", "model_version", "task", "allowed", "reason", "tool_name",
    "passed", "blocked", "sources", "citations", "abstained", "retrieved_count",
    "selected_count", "input_tokens", "output_tokens", "total_tokens", "cost_usd",
    "estimated_input_tokens", "within_budget", "validation_pass", "supported",
)


def safe_value(value, depth=0):
    if depth > 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else safe_value(item, depth + 1)
            for key, item in list(value.items())[:100] if str(key).lower() not in PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [safe_value(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return redact_for_logs(value)[:8000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return safe_value(str(value), depth + 1)


def select(value, keys):
    return safe_value({key: value[key] for key in keys if key in value}) if isinstance(value, dict) else {}


def snapshot(context, trace, response, status):
    events = trace.get("lifecycle") or []
    return {
        "schema_version": 1,
        "request_id": trace.get("request_id"),
        "tenant": context.tenant_id,
        "prompt_version": select(trace.get("prompt"), ("prompt_id", "version", "prompt_key", "modules")),
        "model_version": select(trace.get("model_governance"),
                                ("provider", "model", "model_version", "requested_model", "resolved_model")),
        "intent": safe_value(trace.get("intent")),
        "workflow": safe_value(trace.get("workflow")),
        "tools": [select(call, ("name", "args", "output", "validation_pass", "validation_reason"))
                  for call in (trace.get("tool_calls") or [])[:100]],
        "retrieved_sources": [safe_event(event)
                              for event in events if event.get("stage") == "retrieval"][:100],
        "policy_checks": [safe_event(event)
                          for event in events if event.get("stage") == "validation"][:100],
        "llm_calls": [safe_event(event)
                      for event in events if event.get("stage") == "llm"][:100],
        "final_response": safe_value(response),
        "status": status,
        "redacted": True,
    }


def safe_event(event):
    return {**select(event, ("name", "status")),
            "attributes": select(event.get("attributes"), EVENT_ATTRIBUTES)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def review_categories(request_id, metrics, *, tokens=None, negative_feedback=False):
    categories = []
    if negative_feedback:
        categories.append("negative_feedback")
    if tokens is not None and tokens >= 8000:
        categories.append("high_tokens")
    if metrics.get("escalated"):
        categories.append("escalation")
    if metrics.get("tool_failures", 0) or any(value is False for value in metrics.get("tool_validations", [])):
        categories.append("tool_failure")
    if metrics.get("unsupported_critical_claims", 0) or metrics.get("security_alert"):
        categories.append("security_alert")
    # Stable 5% sample, independent of model self-reported confidence.
    if int(hashlib.sha256(str(request_id).encode()).hexdigest()[:8], 16) % 100 < 5:
        categories.append("sample")
    return categories
