from datetime import datetime

from database import get_connection


class SupportRepository:
    """SQLite access for support ticket data."""

    def insert_support_ticket(self, customer_message: str, agent_summary: str = "", priority: str = "Normal") -> int:
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
