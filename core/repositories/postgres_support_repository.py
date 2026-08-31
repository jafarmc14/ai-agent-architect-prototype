from core.repositories.postgres_connection import get_postgres_connection


PRIORITY_TO_POSTGRES = {
    "Low": "low",
    "Normal": "normal",
    "High": "high",
    "Urgent": "urgent",
}


class PostgresSupportRepository:
    """PostgreSQL access for support ticket data."""

    def insert_support_ticket(
        self,
        customer_message: str,
        agent_summary: str = "",
        priority: str = "Normal",
        user_id: str | None = None,
        tenant_id: str = "default",
        escalation_type: str = "",
        escalation_reason: str = "",
        summarized_context: str = "",
        metadata: dict | None = None,
    ) -> str:
        import psycopg.types.json

        postgres_priority = PRIORITY_TO_POSTGRES.get(priority, priority.lower())
        with get_postgres_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO support_tickets (
                    ticket_number,
                    customer_message,
                    agent_summary,
                    priority,
                    status,
                    user_id,
                    tenant_id,
                    escalation_type,
                    escalation_reason,
                    summarized_context,
                    metadata
                )
                VALUES (
                    'TICKET-' || upper(substr(gen_random_uuid()::text, 1, 8)),
                    %s,
                    %s,
                    %s::support_ticket_priority,
                    'open',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING ticket_number
                """,
                (
                    customer_message,
                    agent_summary,
                    postgres_priority,
                    user_id,
                    tenant_id,
                    escalation_type or None,
                    escalation_reason or None,
                    summarized_context or None,
                    psycopg.types.json.Jsonb(metadata or {}),
                ),
            ).fetchone()
            return row["ticket_number"]
