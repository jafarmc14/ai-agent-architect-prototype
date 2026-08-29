from datetime import datetime

from database import get_connection


class SQLiteSupportRepository:
    """SQLite access for support ticket data."""

    def insert_support_ticket(
        self,
        customer_message: str,
        agent_summary: str = "",
        priority: str = "Normal",
        user_id: str | None = None,
        tenant_id: str = "default",
    ) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO support_tickets (customer_message, agent_summary, priority, status, created_at) VALUES (?, ?, ?, 'Open', ?)",
            (customer_message, agent_summary, priority, datetime.now().isoformat()),
        )
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return ticket_id
