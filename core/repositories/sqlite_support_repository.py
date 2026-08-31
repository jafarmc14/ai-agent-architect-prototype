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
        escalation_type: str = "",
        escalation_reason: str = "",
        summarized_context: str = "",
        metadata: dict | None = None,
    ) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        summary_parts = [
            agent_summary,
            f"Escalation type: {escalation_type}" if escalation_type else "",
            f"Escalation reason: {escalation_reason}" if escalation_reason else "",
            summarized_context,
        ]
        stored_summary = "\n".join(part for part in summary_parts if part)
        cursor.execute(
            "INSERT INTO support_tickets (customer_message, agent_summary, priority, status, created_at) VALUES (?, ?, ?, 'Open', ?)",
            (customer_message, stored_summary, priority, datetime.now().isoformat()),
        )
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return ticket_id
