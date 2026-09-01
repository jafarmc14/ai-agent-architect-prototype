from typing import Any


TOKEN_COMPONENTS = (
    "system_prompt_tokens",
    "user_tokens",
    "conversation_tokens",
    "retrieval_tokens",
    "tool_schema_tokens",
)


def summarize_token_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Aggregate safe numeric token metrics from all LLM spans in one request."""
    llm_events = [
        event for event in trace.get("lifecycle", [])
        if event.get("stage") == "llm" and event.get("name", "").startswith("llm.")
    ]
    summary: dict[str, Any] = {
        "request_id": trace.get("request_id", ""),
        "workflow": trace.get("workflow", ""),
        "request_latency_ms": int(trace.get("request_latency_ms") or 0),
        "llm_calls": len(llm_events),
        "input_tokens": 0,
        "output_tokens": 0,
        "input_budget": 0,
        "context_utilization_ratio": 0.0,
        "within_budget": True,
        "llm_latency_ms": 0,
        "cost_usd": None,
        **{component: 0 for component in TOKEN_COMPONENTS},
    }
    costs = []
    tasks = []
    providers = []
    models = []

    for event in llm_events:
        attributes = event.get("attributes") or {}
        breakdown = attributes.get("token_breakdown") or {}
        for component in TOKEN_COMPONENTS:
            summary[component] += _non_negative_int(breakdown.get(component))
        summary["input_tokens"] += _non_negative_int(breakdown.get("total_input_tokens"))
        summary["output_tokens"] += _non_negative_int(breakdown.get("output_tokens"))
        summary["input_budget"] += _non_negative_int(breakdown.get("input_budget"))
        summary["context_utilization_ratio"] = max(
            summary["context_utilization_ratio"],
            _non_negative_float(breakdown.get("context_utilization_ratio")),
        )
        summary["within_budget"] = summary["within_budget"] and bool(breakdown.get("within_budget", True))
        summary["llm_latency_ms"] += _non_negative_int(attributes.get("latency_ms", event.get("latency_ms")))
        if attributes.get("cost_usd") is not None:
            costs.append(_non_negative_float(attributes["cost_usd"]))
        _append_unique(tasks, breakdown.get("task"))
        _append_unique(providers, attributes.get("provider"))
        _append_unique(models, attributes.get("model"))

    summary["total_tokens"] = summary["input_tokens"] + summary["output_tokens"]
    summary["context_utilization_ratio"] = round(summary["context_utilization_ratio"], 6)
    summary["cost_usd"] = round(sum(costs), 10) if costs else None
    summary["tasks"] = tasks
    summary["providers"] = providers
    summary["models"] = models
    return summary


def _append_unique(values: list[str], value: Any) -> None:
    normalized = str(value or "").strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _non_negative_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0
