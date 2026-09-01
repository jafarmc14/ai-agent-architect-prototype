import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402
from core.repositories.llm_request_repository import LLMRequestRepository  # noqa: E402
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
    "request_traces",
    "trace_spans",
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
        assert migration_count >= 17

        llm_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'llm_requests'
                """
            ).fetchall()
        }
        assert {
            "request_id",
            "trace_id",
            "cost_usd",
            "cost_source",
            "task_type",
            "system_prompt_tokens",
            "user_tokens",
            "conversation_tokens",
            "retrieval_tokens",
            "tool_schema_tokens",
            "estimated_output_tokens",
            "input_budget",
            "output_limit",
            "context_utilization_ratio",
            "within_token_budget",
            "provider_prompt_cache_eligible",
            "cache_read_tokens",
        } <= llm_columns
        assert product_count == 15
        assert order_count == 8

    LLMRequestRepository().insert_request(
        provider="integration",
        model="token-test",
        status="success",
        usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        token_breakdown={
            "task": "intent",
            "system_prompt_tokens": 4,
            "user_tokens": 2,
            "conversation_tokens": 0,
            "retrieval_tokens": 0,
            "tool_schema_tokens": 4,
            "output_tokens": 2,
            "input_budget": 500,
            "output_limit": 128,
            "context_utilization_ratio": 0.02,
            "within_budget": True,
            "provider_prompt_cache_eligible": False,
        },
    )
    with get_postgres_connection() as conn:
        logged = conn.execute(
            "SELECT task_type, system_prompt_tokens, within_token_budget "
            "FROM llm_requests WHERE provider = 'integration' AND model = 'token-test' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert logged and logged["task_type"] == "intent"
        assert logged["system_prompt_tokens"] == 4
        assert logged["within_token_budget"] is True
        conn.execute("DELETE FROM llm_requests WHERE provider = 'integration' AND model = 'token-test'")

    products = PostgresProductRepository().find_products_by_filter(category="Shoes", max_price=1_500_000)
    names = {row["name"] for row in products}
    assert {"Adidas Ultraboost Shoes", "Nike Air Max Shoes", "Birkenstock Sandals"} <= names
    assert all(float(row["price"]) <= 1_500_000 for row in products)

    print("PostgreSQL integration checks passed.")
    print(f"tables={len(tables)}, migrations={migration_count}, products={product_count}, orders={order_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
