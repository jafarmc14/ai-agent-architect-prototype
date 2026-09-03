from datetime import datetime, timedelta, timezone
import json
from typing import Any

from configs import get_settings
from core.repositories.postgres_connection import get_postgres_connection


class ResourceUsageRepository:
    """Atomic PostgreSQL admission checks and request resource accounting."""

    def admit(
        self,
        *,
        request_id: str,
        trace_id: str,
        tenant_id: str,
        identity_key: str,
        session_id: str,
        user_id: str | None,
        workflow: str,
        input_hash: str,
        input_tokens: int,
        limits,
        workflow_limit: int,
        expensive: bool,
    ) -> tuple[bool, str, int | None]:
        if get_settings().database_provider != "postgres":
            raise RuntimeError("PostgreSQL resource repository is unavailable.")

        now = datetime.now(timezone.utc)
        minute_since = now - timedelta(seconds=limits.user_rate_limit_window_seconds)
        repeat_since = now - timedelta(seconds=limits.expensive_repeat_window_seconds)
        day_since = now - timedelta(days=1)
        with get_postgres_connection() as conn:
            with conn.transaction():
                # Tenant lock serializes quota admission across all users in the tenant.
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"resource:tenant:{tenant_id}",))
                user_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM resource_usage_events WHERE identity_key = %s AND created_at >= %s AND status <> 'blocked'",
                    (identity_key, minute_since),
                ).fetchone()["count"]
                workflow_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM resource_usage_events WHERE identity_key = %s AND workflow = %s AND created_at >= %s AND status <> 'blocked'",
                    (identity_key, workflow, minute_since),
                ).fetchone()["count"]
                tenant = conn.execute(
                    """
                    SELECT COUNT(*) AS requests,
                           COALESCE(SUM(input_tokens + output_tokens), 0) AS tokens,
                           COALESCE(SUM(cost_usd), 0) AS cost
                    FROM resource_usage_events
                    WHERE tenant_id = %s AND created_at >= %s AND status <> 'blocked'
                    """,
                    (tenant_id, day_since),
                ).fetchone()
                repeat_count = 0
                if expensive:
                    repeat_count = conn.execute(
                        """
                        SELECT COUNT(*) AS count FROM resource_usage_events
                        WHERE identity_key = %s AND input_hash = %s AND workflow = %s
                          AND created_at >= %s AND status <> 'blocked'
                        """,
                        (identity_key, input_hash, workflow, repeat_since),
                    ).fetchone()["count"]

                code = ""
                retry_after = None
                reserved_cost = (
                    input_tokens * limits.max_input_price_per_million
                    + limits.max_output_tokens * limits.max_output_price_per_million
                ) / 1_000_000
                if user_count >= limits.user_rate_limit_requests:
                    code, retry_after = "user_rate_limit", limits.user_rate_limit_window_seconds
                elif workflow_count >= workflow_limit:
                    code, retry_after = "workflow_rate_limit", limits.user_rate_limit_window_seconds
                elif tenant["requests"] >= limits.tenant_daily_request_quota:
                    code, retry_after = "tenant_request_quota", 3600
                elif int(tenant["tokens"]) + input_tokens > limits.tenant_daily_token_quota:
                    code, retry_after = "tenant_token_quota", 3600
                elif float(tenant["cost"]) + reserved_cost > limits.tenant_daily_cost_quota_usd:
                    code, retry_after = "tenant_cost_quota", 3600
                elif expensive and repeat_count >= limits.expensive_repeat_limit:
                    code, retry_after = "repetitive_expensive_request", limits.expensive_repeat_window_seconds

                self._insert_event(
                    conn,
                    request_id=request_id,
                    trace_id=trace_id,
                    tenant_id=tenant_id,
                    identity_key=identity_key,
                    session_id=session_id,
                    user_id=user_id,
                    workflow=workflow,
                    input_hash=input_hash,
                    status="blocked" if code else "accepted",
                    limit_code=code,
                    input_tokens=input_tokens,
                    cost_usd=0 if code else reserved_cost,
                )
                return not code, code, retry_after

    def finish(self, guard, status: str = "completed", limit_code: str = "") -> None:
        if get_settings().database_provider != "postgres":
            return
        try:
            with get_postgres_connection() as conn:
                conn.execute(
                    """
                    UPDATE resource_usage_events
                    SET status = %s,
                        limit_code = NULLIF(%s, ''),
                        output_tokens = %s,
                        tool_calls = %s,
                        agent_steps = %s,
                        runtime_ms = %s,
                        cost_usd = %s,
                        completed_at = now()
                    WHERE request_id = NULLIF(%s, '')::uuid
                    """,
                    (
                        status,
                        limit_code,
                        guard.output_tokens,
                        guard.tool_calls,
                        guard.agent_steps,
                        int(guard.elapsed_seconds * 1000),
                        guard.cost_usd,
                        guard.request_id,
                    ),
                )
        except Exception:  # noqa: BLE001
            return

    def set_cost_governance(self, request_id: str, metadata: dict[str, Any]) -> None:
        if get_settings().database_provider != "postgres":
            return
        try:
            with get_postgres_connection() as conn:
                conn.execute(
                    """
                    UPDATE resource_usage_events
                    SET metadata = jsonb_set(
                        COALESCE(metadata, '{}'::jsonb),
                        '{cost_governance}',
                        %s::jsonb,
                        true
                    )
                    WHERE request_id = NULLIF(%s, '')::uuid
                    """,
                    (json.dumps(metadata), request_id),
                )
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _insert_event(conn, **values: Any) -> None:
        conn.execute(
            """
            INSERT INTO resource_usage_events (
                request_id, trace_id, tenant_id, identity_key, session_id, user_id, workflow,
                input_hash, status, limit_code, input_tokens, cost_usd
            ) VALUES (
                NULLIF(%s, '')::uuid, NULLIF(%s, '')::uuid, %s, %s, %s, NULLIF(%s, ''), %s,
                %s, %s, NULLIF(%s, ''), %s, %s
            )
            """,
            (
                values["request_id"],
                values["trace_id"],
                values["tenant_id"],
                values["identity_key"],
                values["session_id"],
                values.get("user_id") or "",
                values["workflow"],
                values["input_hash"],
                values["status"],
                values["limit_code"],
                values["input_tokens"],
                values["cost_usd"],
            ),
        )
