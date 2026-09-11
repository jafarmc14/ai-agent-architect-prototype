"""Read-only measured query plans for a configured company; never creates indexes."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import RequestContext, request_context
from core.companies import company_key
from core.repositories.postgres_connection import get_postgres_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--category", default="Shoes")
    parser.add_argument("--max-price", type=float, default=1500000)
    args = parser.parse_args()
    with request_context(RequestContext("query-plan-operator", args.tenant)), get_postgres_connection() as conn:
        conn.execute("SET LOCAL statement_timeout = '5s'")
        result = conn.execute("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT p.id, p.name, p.base_price,
                   COALESCE(sum(i.quantity_on_hand - i.quantity_reserved), 0) AS stock
            FROM products p LEFT JOIN inventory i ON i.product_id = p.id
            WHERE p.is_active AND p.category ILIKE %s AND p.base_price <= %s
            GROUP BY p.id ORDER BY p.base_price LIMIT 20""",
            (f"%{args.category}%", args.max_price)).fetchone()
        print(json.dumps({"company_key": company_key(), "catalog_query": result,
                          "automatic_changes": False}, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
