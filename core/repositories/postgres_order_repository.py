from core.repositories.postgres_connection import get_postgres_connection


STATUS_TO_POSTGRES = {
    "Awaiting Payment": "awaiting_payment",
    "Processing": "processing",
    "Shipped": "shipped",
    "Completed": "completed",
    "Cancelled": "cancelled",
}

POSTGRES_STATUS_SQL = """
CASE o.status::text
    WHEN 'awaiting_payment' THEN 'Awaiting Payment'
    WHEN 'processing' THEN 'Processing'
    WHEN 'shipped' THEN 'Shipped'
    WHEN 'completed' THEN 'Completed'
    WHEN 'cancelled' THEN 'Cancelled'
    ELSE o.status::text
END
"""


class PostgresOrderRepository:
    """PostgreSQL access for order data."""

    def find_order_with_product(self, order_id: str):
        with get_postgres_connection() as conn:
            return conn.execute(
                f"""
                SELECT
                    o.order_number AS id,
                    o.customer_name,
                    COALESCE(oi.product_name, 'Unknown product') AS product_name,
                    COALESCE(oi.quantity, 0) AS quantity,
                    o.grand_total AS total_price,
                    {POSTGRES_STATUS_SQL} AS status,
                    o.shipping_address,
                    o.order_date::date::text AS order_date,
                    o.estimated_arrival::date::text AS estimated_arrival
                FROM orders o
                LEFT JOIN LATERAL (
                    SELECT product_name, quantity
                    FROM order_items
                    WHERE order_id = o.id
                    ORDER BY created_at, id
                    LIMIT 1
                ) oi ON true
                WHERE upper(o.order_number) = upper(%s)
                """,
                (order_id,),
            ).fetchone()

    def find_order_for_update(self, order_id: str):
        with get_postgres_connection() as conn:
            return conn.execute(
                f"""
                SELECT
                    o.order_number AS id,
                    {POSTGRES_STATUS_SQL} AS status,
                    o.customer_name,
                    o.shipping_address
                FROM orders o
                WHERE upper(o.order_number) = upper(%s)
                """,
                (order_id,),
            ).fetchone()

    def update_order_status(self, order_id: str, status: str) -> None:
        postgres_status = STATUS_TO_POSTGRES.get(status, status.lower().replace(" ", "_"))
        with get_postgres_connection() as conn:
            conn.execute(
                """
                UPDATE orders
                SET status = %s::order_status,
                    updated_at = now()
                WHERE upper(order_number) = upper(%s)
                """,
                (postgres_status, order_id),
            )

    def update_order_shipping_address(self, order_id: str, new_address: str) -> None:
        with get_postgres_connection() as conn:
            conn.execute(
                """
                UPDATE orders
                SET shipping_address = %s,
                    updated_at = now()
                WHERE upper(order_number) = upper(%s)
                """,
                (new_address, order_id),
            )
