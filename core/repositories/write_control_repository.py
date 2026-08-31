from typing import Any

from configs import get_settings
from core.repositories.postgres_connection import get_postgres_connection


class WriteControlRepository:
    """Persistence for idempotency records and audit logs."""

    def find_idempotency_record(self, idempotency_key: str, tenant_id: str = "default") -> dict[str, Any] | None:
        if get_settings().database_provider != "postgres":
            return None
        with get_postgres_connection() as conn:
            return conn.execute(
                """
                SELECT idempotency_key, action, resource_type, resource_id, request_id, user_id, status, response, metadata
                FROM write_idempotency_keys
                WHERE tenant_id = %s
                  AND idempotency_key = %s
                """,
                (tenant_id, idempotency_key),
            ).fetchone()

    def record_idempotency(
        self,
        *,
        idempotency_key: str,
        action: str,
        resource_type: str,
        resource_id: str = "",
        request_id: str = "",
        user_id: str | None = None,
        tenant_id: str = "default",
        response: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if get_settings().database_provider != "postgres":
            return
        import psycopg.types.json

        with get_postgres_connection() as conn:
            conn.execute(
                """
                INSERT INTO write_idempotency_keys (
                    tenant_id, idempotency_key, action, resource_type, resource_id,
                    request_id, user_id, status, response, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::uuid, 'completed', %s, %s)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                """,
                (
                    tenant_id,
                    idempotency_key,
                    action,
                    resource_type,
                    resource_id or None,
                    request_id or None,
                    user_id,
                    response,
                    psycopg.types.json.Jsonb(metadata or {}),
                ),
            )

    def insert_audit_log(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str = "",
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        request_id: str = "",
        idempotency_key: str = "",
        actor_user_id: str | None = None,
        actor_role: str = "anonymous",
        tenant_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if get_settings().database_provider != "postgres":
            return
        import psycopg.types.json

        with get_postgres_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    tenant_id, actor_user_id, actor_role, action, resource_type,
                    resource_id, old_value, new_value, request_id, idempotency_key, metadata
                )
                VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    actor_user_id,
                    actor_role,
                    action,
                    resource_type,
                    resource_id or None,
                    psycopg.types.json.Jsonb(old_value or {}),
                    psycopg.types.json.Jsonb(new_value or {}),
                    request_id or None,
                    idempotency_key or None,
                    psycopg.types.json.Jsonb(metadata or {}),
                ),
            )
