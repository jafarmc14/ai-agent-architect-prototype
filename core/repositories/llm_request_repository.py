from typing import Any

from configs import get_settings
from core.repositories.postgres_connection import get_postgres_connection


class LLMRequestRepository:
    """Best-effort logging for provider calls and prompt versions."""

    def insert_request(
        self,
        *,
        provider: str,
        model: str,
        model_version: str = "",
        model_metadata: dict[str, Any] | None = None,
        request_messages: list[dict[str, Any]] | None = None,
        request_tools: list[Any] | None = None,
        response_text: str = "",
        response_tool_calls: list[dict[str, Any]] | None = None,
        status: str = "success",
        error_code: str = "",
        error_message: str = "",
        latency_ms: int | None = None,
        usage: dict[str, Any] | None = None,
        cost_usd: float | None = None,
        cost_source: str = "",
        request_id: str = "",
        trace_id: str = "",
        prompt_metadata: dict[str, Any] | None = None,
        token_breakdown: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if get_settings().database_provider != "postgres":
            return

        import psycopg.types.json

        prompt_metadata = prompt_metadata or {}
        usage = usage or {}
        metadata = metadata or {}
        token_breakdown = token_breakdown or {}
        metadata["prompt"] = prompt_metadata
        metadata["model"] = model_metadata or {
            "provider": provider,
            "model": model,
            "model_version": model_version,
            "pinned": False,
            "alias": True,
        }
        try:
            with get_postgres_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO llm_requests (
                        provider, model, model_version, model_key, model_pinned,
                        request_id, trace_id, cost_usd, cost_source,
                        request_messages, request_tools,
                        response_text, response_tool_calls, status, error_code, error_message,
                        latency_ms, prompt_tokens, completion_tokens, total_tokens,
                        task_type, system_prompt_tokens, user_tokens, conversation_tokens,
                        retrieval_tokens, tool_schema_tokens, estimated_output_tokens,
                        input_budget, output_limit, context_utilization_ratio,
                        within_token_budget, provider_prompt_cache_eligible,
                        cache_read_tokens, cache_creation_tokens,
                        prompt_id, prompt_version, prompt_key, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        NULLIF(%s, '')::uuid, NULLIF(%s, '')::uuid, %s, NULLIF(%s, ''),
                        %s::jsonb, %s::jsonb,
                        %s, %s::jsonb, %s::llm_request_status, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    """,
                    (
                        provider,
                        model,
                        model_version or metadata["model"].get("model_version"),
                        _model_key(provider, model, model_version or metadata["model"].get("model_version", "")),
                        bool(metadata["model"].get("pinned")),
                        request_id,
                        trace_id,
                        cost_usd,
                        cost_source,
                        psycopg.types.json.Jsonb(request_messages or []),
                        psycopg.types.json.Jsonb(_safe_tools(request_tools or [])),
                        response_text,
                        psycopg.types.json.Jsonb(response_tool_calls or []),
                        status,
                        error_code or None,
                        error_message or None,
                        latency_ms,
                        _usage_value(usage, "input_tokens", "prompt_tokens"),
                        _usage_value(usage, "output_tokens", "completion_tokens"),
                        _usage_value(usage, "total_tokens"),
                        token_breakdown.get("task"),
                        token_breakdown.get("system_prompt_tokens"),
                        token_breakdown.get("user_tokens"),
                        token_breakdown.get("conversation_tokens"),
                        token_breakdown.get("retrieval_tokens"),
                        token_breakdown.get("tool_schema_tokens"),
                        token_breakdown.get("output_tokens"),
                        token_breakdown.get("input_budget"),
                        token_breakdown.get("output_limit"),
                        token_breakdown.get("context_utilization_ratio"),
                        token_breakdown.get("within_budget"),
                        token_breakdown.get("provider_prompt_cache_eligible"),
                        _nested_usage_value(usage, "cache_read", "cached_tokens"),
                        _nested_usage_value(usage, "cache_creation", "cache_creation_input_tokens"),
                        prompt_metadata.get("prompt_id"),
                        prompt_metadata.get("version"),
                        prompt_metadata.get("prompt_key"),
                        psycopg.types.json.Jsonb(metadata),
                    ),
                )
        except Exception:  # noqa: BLE001
            return


def _usage_value(usage: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            return parsed if parsed >= 0 else None
    return None


def _nested_usage_value(usage: dict[str, Any], *keys: str) -> int | None:
    containers = [usage]
    for name in ("input_token_details", "prompt_tokens_details", "usage_metadata"):
        value = usage.get(name)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        value = _usage_value(container, *keys)
        if value is not None:
            return value
    return None


def _safe_tools(tools: list[Any]) -> list[Any]:
    safe = []
    for tool in tools:
        safe.append({
            "name": getattr(tool, "name", getattr(tool, "__name__", str(tool))),
            "description": getattr(tool, "description", "")[:500],
        })
    return safe


def _model_key(provider: str, model: str, model_version: str) -> str:
    return f"{provider}:{model}:{model_version or 'unknown'}"
