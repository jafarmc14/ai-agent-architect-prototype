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
    ) -> str:
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
                    tenant_id
                )
                VALUES (
                    'TICKET-' || upper(substr(gen_random_uuid()::text, 1, 8)),
                    %s,
                    %s,
                    %s::support_ticket_priority,
                    'open',
                    %s,
                    %s
                )
                RETURNING ticket_number
                """,
                (customer_message, agent_summary, postgres_priority, user_id, tenant_id),
            ).fetchone()
            return row["ticket_number"]
