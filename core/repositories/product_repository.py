from database import get_connection


class ProductRepository:
    """SQLite access for product catalog data."""

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
