from core.repositories.postgres_connection import get_postgres_connection


class PostgresCartRepository:
    """PostgreSQL access for shopping cart data."""

    def find_cart_item(self, session_id: str, product_id: str, user_id: str | None = None):
        with get_postgres_connection() as conn:
            return conn.execute(
                """
                SELECT sci.id, sci.quantity
                FROM shopping_cart_items sci
                JOIN shopping_carts sc ON sc.id = sci.shopping_cart_id
                WHERE (
                    (%s::uuid IS NOT NULL AND sc.user_id = %s::uuid)
                    OR (%s::uuid IS NULL AND sc.session_id = %s)
                )
                  AND sci.product_id = %s
                """,
                (user_id, user_id, user_id, session_id, product_id),
            ).fetchone()

    def update_cart_quantity(self, cart_item_id: str, quantity: int) -> None:
        with get_postgres_connection() as conn:
            conn.execute(
                """
                UPDATE shopping_cart_items
                SET quantity = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (quantity, cart_item_id),
            )

    def insert_cart_item(self, session_id: str, product_id: str, quantity: int, user_id: str | None = None) -> None:
        with get_postgres_connection() as conn:
            cart = self._get_or_create_cart(conn, session_id, user_id)
            product = conn.execute(
                "SELECT base_price AS price FROM products WHERE id = %s",
                (product_id,),
            ).fetchone()

            conn.execute(
                """
                INSERT INTO shopping_cart_items (
                    shopping_cart_id,
                    product_id,
                    quantity,
                    unit_price,
                    currency
                )
                VALUES (%s, %s, %s, %s, 'IDR')
                ON CONFLICT (shopping_cart_id, product_id, product_variant_id)
                DO UPDATE SET
                    quantity = shopping_cart_items.quantity + EXCLUDED.quantity,
                    updated_at = now()
                """,
                (cart["id"], product_id, quantity, product["price"]),
            )

    def list_cart_items(self, session_id: str, user_id: str | None = None):
        with get_postgres_connection() as conn:
            return conn.execute(
                """
                SELECT
                    p.name,
                    sci.unit_price AS price,
                    sci.quantity,
                    (sci.unit_price * sci.quantity) AS subtotal
                FROM shopping_cart_items sci
                JOIN shopping_carts sc ON sc.id = sci.shopping_cart_id
                JOIN products p ON p.id = sci.product_id
                WHERE (
                    (%s::uuid IS NOT NULL AND sc.user_id = %s::uuid)
                    OR (%s::uuid IS NULL AND sc.session_id = %s)
                )
                ORDER BY sci.added_at, sci.id
                """,
                (user_id, user_id, user_id, session_id),
            ).fetchall()

    def delete_cart_items(self, session_id: str, user_id: str | None = None) -> int:
        with get_postgres_connection() as conn:
            result = conn.execute(
                """
                DELETE FROM shopping_cart_items sci
                USING shopping_carts sc
                WHERE sc.id = sci.shopping_cart_id
                  AND (
                      (%s::uuid IS NOT NULL AND sc.user_id = %s::uuid)
                      OR (%s::uuid IS NULL AND sc.session_id = %s)
                  )
                """,
                (user_id, user_id, user_id, session_id),
            )
            return result.rowcount or 0

    def _get_or_create_cart(self, conn, session_id: str, user_id: str | None = None):
        if user_id:
            cart = conn.execute(
                """
                SELECT id
                FROM shopping_carts
                WHERE user_id = %s
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if cart:
                return cart
            return conn.execute(
                """
                INSERT INTO shopping_carts (user_id, session_id, currency)
                VALUES (%s, %s, 'IDR')
                RETURNING id
                """,
                (user_id, session_id),
            ).fetchone()

        return conn.execute(
            """
            INSERT INTO shopping_carts (session_id, currency)
            VALUES (%s, 'IDR')
            ON CONFLICT (session_id) DO UPDATE SET updated_at = now()
            RETURNING id
            """,
            (session_id,),
        ).fetchone()
