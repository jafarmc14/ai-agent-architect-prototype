from database import get_connection


class SQLiteOrderRepository:
    """SQLite access for order data."""

    def find_order_with_product(self, order_id: str, user_id: str | None = None):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT o.id, p.name as product_name, o.quantity, o.total_price,
                      o.status, o.order_date, o.estimated_arrival
               FROM orders o
               JOIN products p ON o.product_id = p.id
               WHERE UPPER(o.id) = UPPER(?)""",
            (order_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def find_order_for_update(self, order_id: str, user_id: str | None = None):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, status, customer_name, shipping_address FROM orders WHERE UPPER(id) = UPPER(?)",
            (order_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def update_order_status(self, order_id: str, status: str, user_id: str | None = None) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = ? WHERE UPPER(id) = UPPER(?)",
            (status, order_id),
        )
        conn.commit()
        conn.close()

    def update_order_shipping_address(self, order_id: str, new_address: str, user_id: str | None = None) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET shipping_address = ? WHERE UPPER(id) = UPPER(?)",
            (new_address, order_id),
        )
        conn.commit()
        conn.close()
