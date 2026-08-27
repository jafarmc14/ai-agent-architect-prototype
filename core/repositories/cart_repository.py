from datetime import datetime

from database import get_connection


class CartRepository:
    """SQLite access for shopping cart data."""

    def find_cart_item(self, session_id: str, product_id: int):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, quantity FROM shopping_cart WHERE session_id = ? AND product_id = ?",
            (session_id, product_id),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def update_cart_quantity(self, cart_item_id: int, quantity: int) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE shopping_cart SET quantity = ? WHERE id = ?", (quantity, cart_item_id))
        conn.commit()
        conn.close()

    def insert_cart_item(self, session_id: str, product_id: int, quantity: int) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shopping_cart (session_id, product_id, quantity, added_at) VALUES (?, ?, ?, ?)",
            (session_id, product_id, quantity, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    def list_cart_items(self, session_id: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT p.name, p.price, c.quantity, (p.price * c.quantity) as subtotal
               FROM shopping_cart c
               JOIN products p ON c.product_id = p.id
               WHERE c.session_id = ?""",
            (session_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def delete_cart_items(self, session_id: str) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shopping_cart WHERE session_id = ?", (session_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
