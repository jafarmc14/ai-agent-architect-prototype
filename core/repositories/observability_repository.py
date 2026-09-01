from datetime import datetime, timezone
from typing import Any

from configs import get_settings
from core.repositories.postgres_connection import get_postgres_connection


_MEMORY_REQUEST_TRACES: dict[str, dict[str, Any]] = {}
_MEMORY_TRACE_SPANS: list[dict[str, Any]] = []


class ObservabilityRepository:
    """Persists request traces and spans with an in-memory test fallback."""

    def start_request(self, **payload: Any) -> None:
        if get_settings().database_provider != "postgres":
            _MEMORY_REQUEST_TRACES[payload["request_id"]] = {
                **payload,
                "status": "running",
                "started_at": datetime.now(timezone.utc),
            }
            return

        try:
            with get_postgres_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO request_traces (
                        request_id, trace_id, session_id, tenant_id, user_id, request_input, status
                    )
                    VALUES (%s, %s, %s, %s, NULLIF(%s, ''), %s, 'running')
                    """,
                    (
                        payload["request_id"],
                        payload["trace_id"],
                        payload.get("session_id"),
                        payload.get("tenant_id", "default"),
                        payload.get("user_id", ""),
                        payload.get("request_input", ""),
                    ),
                )
        except Exception:  # noqa: BLE001
            return

    def finish_request(self, **payload: Any) -> None:
        if get_settings().database_provider != "postgres":
            row = _MEMORY_REQUEST_TRACES.setdefault(payload["request_id"], {})
            row.update(payload)
            row["finished_at"] = datetime.now(timezone.utc)
            return

        try:
            with get_postgres_connection() as conn:
                conn.execute(
                    """
                    UPDATE request_traces
                    SET status = %s,
                        response_output = %s,
                        intent = NULLIF(%s, ''),
                        workflow = NULLIF(%s, ''),
                        conversation_id = NULLIF(%s, '')::uuid,
                        latency_ms = %s,
                        error_message = NULLIF(%s, ''),
                        finished_at = now()
                    WHERE request_id = %s
                    """,
                    (
                        payload.get("status", "success"),
                        payload.get("response_output", ""),
                        payload.get("intent", ""),
                        payload.get("workflow", ""),
                        payload.get("conversation_id", ""),
                        payload.get("latency_ms"),
                        payload.get("error_message", ""),
                        payload["request_id"],
                    ),
                )
        except Exception:  # noqa: BLE001
            return

    def insert_span(self, **payload: Any) -> None:
        if get_settings().database_provider != "postgres":
            _MEMORY_TRACE_SPANS.append(dict(payload))
            return

        import psycopg.types.json

        try:
            with get_postgres_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO trace_spans (
                        id, trace_id, parent_span_id, stage, name, status,
                        started_at, finished_at, latency_ms, attributes, error_message
                    )
                    VALUES (
                        %s, %s, NULLIF(%s, '')::uuid, %s, %s, %s,
                        %s, %s, %s, %s::jsonb, NULLIF(%s, '')
                    )
                    """,
                    (
                        payload["span_id"],
                        payload["trace_id"],
                        payload.get("parent_span_id", ""),
                        payload["stage"],
                        payload["name"],
                        payload.get("status", "success"),
                        payload["started_at"],
                        datetime.now(timezone.utc),
                        payload.get("latency_ms"),
                        psycopg.types.json.Jsonb(payload.get("attributes", {})),
                        payload.get("error_message", ""),
                    ),
                )
        except Exception:  # noqa: BLE001
            return

    def memory_snapshot(self) -> dict[str, Any]:
        return {
            "requests": {key: dict(value) for key, value in _MEMORY_REQUEST_TRACES.items()},
            "spans": [dict(value) for value in _MEMORY_TRACE_SPANS],
        }

    def reset_memory(self) -> None:
        _MEMORY_REQUEST_TRACES.clear()
        _MEMORY_TRACE_SPANS.clear()
