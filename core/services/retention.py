from datetime import datetime, timedelta, timezone

from configs.retention import RetentionPolicy
from core.repositories.postgres_connection import get_postgres_connection


def run_retention(tenant_id, *, policy=None, apply=False):
    """Operator-only job, bounded per table; never delete operational orders/users."""
    if not tenant_id or not tenant_id.strip():
        raise ValueError("An explicit tenant is required")
    policy = policy or RetentionPolicy()
    now = datetime.now(timezone.utc)
    # Delete free-text rows at the stricter PII deadline: regex redaction is not anonymization.
    targets = (
        ("messages", "id", "created_at", min(policy.raw_conversation_days, policy.pii_days)),
        ("llm_requests", "id", "created_at", max(policy.log_days, 35)),
        ("evaluation_results", "id", "created_at", min(policy.evaluation_days, policy.pii_days)),
        ("audit_logs", "id", "created_at", policy.audit_days),
        ("decision_records", "request_id", "created_at", policy.audit_days),
        ("action_approvals", "confirmation_id", "expires_at", policy.pii_days),
    )
    result = {"tenant_id": tenant_id, "apply": apply, "held": False, "batch_size": policy.batch_size, "rows": {}}
    with get_postgres_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"retention:{tenant_id}",))
        if conn.execute("SELECT 1 FROM retention_holds WHERE tenant_id = %s", (tenant_id,)).fetchone():
            result["held"] = True
            return result
        scrubs = (
            ("llm_requests", "id", "created_at",
             "request_messages = NULL, request_tools = NULL, response_text = NULL, response_tool_calls = NULL, error_message = NULL, metadata = '{}'::jsonb",
             "(request_messages IS NOT NULL OR request_tools IS NOT NULL OR response_text IS NOT NULL OR response_tool_calls IS NOT NULL OR error_message IS NOT NULL OR metadata != '{}'::jsonb)"),
            ("request_traces", "request_id", "started_at",
             "request_input = NULL, response_output = NULL, error_message = NULL, metadata = '{}'::jsonb",
             "finished_at IS NOT NULL AND (request_input IS NOT NULL OR response_output IS NOT NULL OR error_message IS NOT NULL OR metadata != '{}'::jsonb)"),
            ("conversations", "id", "updated_at",
             "structured_state = '{}'::jsonb, metadata = '{}'::jsonb",
             "(structured_state != '{}'::jsonb OR metadata != '{}'::jsonb)"),
        )
        for table, key, timestamp, assignments, condition in scrubs:
            selection = f"SELECT {key} FROM {table} WHERE tenant_id = %s AND {timestamp} < %s AND {condition} ORDER BY {timestamp}, {key} LIMIT %s"
            parameters = (tenant_id, now - timedelta(days=policy.pii_days), policy.batch_size)
            if apply:
                rows = conn.execute(f"UPDATE {table} SET {assignments} WHERE tenant_id = %s AND {key} IN ({selection}) RETURNING {key}",
                                    (tenant_id, *parameters)).fetchall()
            else:
                rows = conn.execute(selection, parameters).fetchall()
            result["rows"][table + "_content_scrubbed"] = len(rows)
        span_selection = """SELECT s.id FROM trace_spans s JOIN request_traces r USING (trace_id)
            WHERE r.tenant_id = %s AND s.started_at < %s ORDER BY s.started_at, s.id LIMIT %s"""
        params = (tenant_id, now - timedelta(days=min(policy.log_days, policy.pii_days)), policy.batch_size)
        rows = conn.execute(("DELETE FROM trace_spans WHERE id IN (" + span_selection + ") RETURNING id")
                            if apply else span_selection, params).fetchall()
        result["rows"]["trace_spans"] = len(rows)
        for table, key, timestamp, days in targets:
            cutoff = now - timedelta(days=days)
            # Identifiers are internal constants, never configuration or request input.
            selection = f"SELECT {key} FROM {table} WHERE tenant_id = %s AND {timestamp} < %s ORDER BY {timestamp}, {key} LIMIT %s"
            if apply:
                sql = f"DELETE FROM {table} WHERE tenant_id = %s AND {key} IN ({selection}) RETURNING {key}"
                rows = conn.execute(sql, (tenant_id, tenant_id, cutoff, policy.batch_size)).fetchall()
            else:
                rows = conn.execute(selection, (tenant_id, cutoff, policy.batch_size)).fetchall()
            result["rows"][table] = len(rows)
        if apply:
            from psycopg.types.json import Jsonb
            conn.execute("""INSERT INTO audit_logs (tenant_id, actor_role, action, resource_type, new_value)
                VALUES (%s,'retention_operator','data.retention','tenant',%s)""",
                (tenant_id, Jsonb({"counts": result["rows"], "policy": policy.model_dump()})))
    return result
