from datetime import datetime

from database import get_connection


class StoreRepository:
    """SQLite data access for store products, orders, carts, and tickets."""

    def find_products_by_name(self, product_name: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, category, price, stock, country FROM products WHERE LOWER(name) LIKE LOWER(?)",
            (f"%{product_name}%",),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def find_products_by_filter(self, category: str = "", max_price: float = 0, min_price: float = 0):
        conn = get_connection()
        cursor = conn.cursor()

        query = "SELECT name, category, price, stock, country FROM products WHERE 1=1"
        params = []

        if category:
            query += " AND LOWER(category) LIKE LOWER(?)"
            params.append(f"%{category}%")
        if min_price > 0:
            query += " AND price >= ?"
            params.append(min_price)
        if max_price > 0:
            query += " AND price <= ?"
            params.append(max_price)

        query += " ORDER BY price ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def find_order_with_product(self, order_id: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT o.id, o.customer_name, p.name as product_name, o.quantity, o.total_price,
                      o.status, o.shipping_address, o.order_date, o.estimated_arrival
               FROM orders o
               JOIN products p ON o.product_id = p.id
               WHERE UPPER(o.id) = UPPER(?)""",
            (order_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def find_order_for_update(self, order_id: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, status, customer_name, shipping_address FROM orders WHERE UPPER(id) = UPPER(?)",
            (order_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return row

    def update_order_status(self, order_id: str, status: str) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = ? WHERE UPPER(id) = UPPER(?)",
            (status, order_id),
        )
        conn.commit()
        conn.close()

    def update_order_shipping_address(self, order_id: str, new_address: str) -> None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET shipping_address = ? WHERE UPPER(id) = UPPER(?)",
            (new_address, order_id),
        )
        conn.commit()
        conn.close()

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
