from core.repositories.postgres_connection import get_postgres_connection


class PostgresProductRepository:
    """PostgreSQL access for product catalog data."""

    def find_products_by_name(self, product_name: str):
        with get_postgres_connection() as conn:
            return conn.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p.category,
                    p.base_price AS price,
                    COALESCE(SUM(i.quantity_on_hand - i.quantity_reserved), 0)::int AS stock,
                    p.country_of_origin AS country
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE p.name ILIKE %s
                  AND p.is_active = true
                GROUP BY p.id, p.name, p.category, p.base_price, p.country_of_origin
                ORDER BY p.name
                """,
                (f"%{product_name}%",),
            ).fetchall()

    def find_products_by_filter(self, category: str = "", max_price: float = 0, min_price: float = 0):
        conditions = ["p.is_active = true"]
        params = []

        if category:
            conditions.append("p.category ILIKE %s")
            params.append(f"%{category}%")
        if min_price > 0:
            conditions.append("p.base_price >= %s")
            params.append(min_price)
        if max_price > 0:
            conditions.append("p.base_price <= %s")
            params.append(max_price)

        where_clause = " AND ".join(conditions)
        with get_postgres_connection() as conn:
            return conn.execute(
                f"""
                SELECT
                    p.name,
                    p.category,
                    p.base_price AS price,
                    COALESCE(SUM(i.quantity_on_hand - i.quantity_reserved), 0)::int AS stock,
                    p.country_of_origin AS country
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE {where_clause}
                GROUP BY p.id, p.name, p.category, p.base_price, p.country_of_origin
                ORDER BY p.base_price ASC
                """,
                tuple(params),
            ).fetchall()
