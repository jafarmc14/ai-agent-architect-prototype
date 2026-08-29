from core.repositories.postgres_connection import get_postgres_connection


class UserRepository:
    """Read user identities used by session authentication."""

    def list_customer_users(self) -> list[dict]:
        with get_postgres_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, external_id, name, email, metadata
                FROM users
                WHERE COALESCE(metadata->>'role', 'customer') = 'customer'
                ORDER BY name, email
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def find_user_by_id(self, user_id: str):
        with get_postgres_connection() as conn:
            row = conn.execute(
                """
                SELECT id, external_id, name, email, metadata
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
