import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402
from core.repositories.postgres_connection import get_postgres_connection  # noqa: E402
from core.repositories.postgres_product_repository import PostgresProductRepository  # noqa: E402


REQUIRED_TABLES = {
    "users",
    "products",
    "inventory",
    "orders",
    "shopping_carts",
    "support_tickets",
    "documents",
    "document_chunks",
    "conversations",
    "messages",
    "llm_requests",
    "evaluation_runs",
    "evaluation_results",
}


def main() -> int:
    settings = get_settings()
    assert settings.database_provider == "postgres", "Integration test requires DATABASE_PROVIDER=postgres."

    with get_postgres_connection() as conn:
        table_rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
        tables = {row["table_name"] for row in table_rows}
        missing = sorted(REQUIRED_TABLES - tables)
        assert not missing, f"Missing PostgreSQL tables: {missing}"

        vector_enabled = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS enabled"
        ).fetchone()["enabled"]
        assert vector_enabled is True, "pgvector extension is not enabled."

        migration_count = conn.execute("SELECT count(*) AS count FROM schema_migrations").fetchone()["count"]
        product_count = conn.execute("SELECT count(*) AS count FROM products").fetchone()["count"]
        order_count = conn.execute("SELECT count(*) AS count FROM orders").fetchone()["count"]
        assert migration_count >= 14
        assert product_count == 15
        assert order_count == 8

    products = PostgresProductRepository().find_products_by_filter(category="Shoes", max_price=1_500_000)
    names = {row["name"] for row in products}
    assert {"Adidas Ultraboost Shoes", "Nike Air Max Shoes", "Birkenstock Sandals"} <= names
    assert all(float(row["price"]) <= 1_500_000 for row in products)

    print("PostgreSQL integration checks passed.")
    print(f"tables={len(tables)}, migrations={migration_count}, products={product_count}, orders={order_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
