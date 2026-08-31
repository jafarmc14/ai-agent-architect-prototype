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
        prompt_metadata: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if get_settings().database_provider != "postgres":
            return

        import psycopg.types.json

        prompt_metadata = prompt_metadata or {}
        usage = usage or {}
        metadata = metadata or {}
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
                        request_messages, request_tools,
                        response_text, response_tool_calls, status, error_code, error_message,
                        latency_ms, prompt_tokens, completion_tokens, total_tokens,
                        prompt_id, prompt_version, prompt_key, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb,
                        %s, %s::jsonb, %s::llm_request_status, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    """,
                    (
                        provider,
                        model,
                        model_version or metadata["model"].get("model_version"),
                        _model_key(provider, model, model_version or metadata["model"].get("model_version", "")),
                        bool(metadata["model"].get("pinned")),
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
            return int(value)
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
