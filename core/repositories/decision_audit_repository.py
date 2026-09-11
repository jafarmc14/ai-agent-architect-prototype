from psycopg.types.json import Jsonb

from core.auth import get_request_context
from core.repositories.postgres_connection import get_postgres_connection
from core.services.decision_audit import digest


class DecisionAuditRepository:
    def record(self, value):
        context = get_request_context()
        if value.get("tenant") != context.tenant_id:
            raise PermissionError("Audit tenant does not match request context")
        with get_postgres_connection() as conn:
            conn.execute("""INSERT INTO decision_records
                (tenant_id, request_id, actor_user_id, snapshot, snapshot_sha256)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id, request_id) DO NOTHING""",
                (context.tenant_id, value["request_id"], context.user_id, Jsonb(value), digest(value)))

    def reconstruct(self, request_id):
        context = get_request_context()
        if context.role not in {"manager", "admin"}:
            raise PermissionError("Incident reconstruction requires manager or admin")
        with get_postgres_connection() as conn:
            row = conn.execute("""SELECT request_id, actor_user_id, created_at, snapshot, snapshot_sha256
                FROM decision_records WHERE tenant_id = %s AND request_id = %s""",
                (context.tenant_id, request_id)).fetchone()
        if row:
            row["integrity_verified"] = digest(row["snapshot"]) == row["snapshot_sha256"]
        return row
