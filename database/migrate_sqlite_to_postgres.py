import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402


MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations" / "postgres"

ORDER_STATUS_MAP = {
    "Awaiting Payment": "awaiting_payment",
    "Processing": "processing",
    "Shipped": "shipped",
    "Completed": "completed",
    "Cancelled": "cancelled",
}

TICKET_PRIORITY_MAP = {
    "Low": "low",
    "Normal": "normal",
    "High": "high",
    "Urgent": "urgent",
}

TICKET_STATUS_MAP = {
    "Open": "open",
    "In Progress": "in_progress",
    "Resolved": "resolved",
    "Closed": "closed",
}


def import_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Missing PostgreSQL driver. Install it with: py -m pip install psycopg[binary]"
        ) from exc
    return psycopg


def sqlite_rows(sqlite_path: Path, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def schema_migrations_exists(pg_conn) -> bool:
    existing = pg_conn.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'schema_migrations'
        )
        """
    ).fetchone()[0]
    return existing


def migration_applied(pg_conn, version: str) -> bool:
    if not schema_migrations_exists(pg_conn):
        return False
    return pg_conn.execute(
        "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = %s)",
        (version,),
    ).fetchone()[0]


def apply_schema(pg_conn) -> None:
    for path in sorted(MIGRATIONS_DIR.glob("V*.sql")):
        version = path.name.split("__", 1)[0]
        applied = pg_conn.execute(
            "SELECT %s",
            (migration_applied(pg_conn, version),),
        ).fetchone()[0]
        if applied:
            continue
        pg_conn.execute(path.read_text(encoding="utf-8"))


def clear_target(pg_conn) -> None:
    pg_conn.execute(
        """
        TRUNCATE TABLE
            support_tickets,
            shopping_cart_items,
            shopping_carts,
            order_items,
            orders,
            inventory,
            product_variants,
            products
        RESTART IDENTITY CASCADE
        """
    )


def ensure_demo_user(pg_conn, customer_name: str | None):
    if not customer_name:
        return None, None
    row = pg_conn.execute(
        """
        INSERT INTO users (external_id, name, email, metadata)
        VALUES (
            'demo-' || lower(regexp_replace(%s, '[^a-zA-Z0-9]+', '-', 'g')),
            %s,
            lower(regexp_replace(%s, '[^a-zA-Z0-9]+', '.', 'g')) || '@example.local',
            jsonb_build_object('role', 'customer', 'tenant_id', 'default', 'source', 'demo_seed')
        )
        ON CONFLICT (email) DO UPDATE SET
            name = EXCLUDED.name,
            metadata = users.metadata || EXCLUDED.metadata,
            updated_at = now()
        RETURNING id, email
        """,
        (customer_name, customer_name, customer_name),
    ).fetchone()
    return row[0], row[1]


def migrate_products(pg_conn, sqlite_path: Path) -> dict[int, str]:
    product_id_map = {}
    rows = sqlite_rows(
        sqlite_path,
        "SELECT id, name, category, price, stock, country FROM products ORDER BY id",
    )

    for row in rows:
        sku = f"SQLITE-PROD-{row['id']:04d}"
        result = pg_conn.execute(
            """
            INSERT INTO products (
                sku, name, category, country_of_origin, base_price, currency, is_active, metadata
            )
            VALUES (%s, %s, %s, %s, %s, 'IDR', true, %s::jsonb)
            ON CONFLICT (sku) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                country_of_origin = EXCLUDED.country_of_origin,
                base_price = EXCLUDED.base_price,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (
                sku,
                row["name"],
                row["category"],
                row["country"],
                row["price"],
                json.dumps({"source": "sqlite", "sqlite_product_id": row["id"]}),
            ),
        ).fetchone()
        product_id_map[row["id"]] = result[0]

    return product_id_map


def migrate_inventory(pg_conn, sqlite_path: Path, product_id_map: dict[int, str]) -> int:
    rows = sqlite_rows(sqlite_path, "SELECT id, stock FROM products ORDER BY id")

    for row in rows:
        product_id = product_id_map[row["id"]]
        pg_conn.execute(
            """
            INSERT INTO inventory (
                product_id, product_variant_id, location_code, quantity_on_hand, quantity_reserved
            )
            SELECT %s, NULL, 'default', %s, 0
            WHERE NOT EXISTS (
                SELECT 1 FROM inventory
                WHERE product_id = %s
                  AND product_variant_id IS NULL
                  AND location_code = 'default'
            )
            """,
            (product_id, row["stock"], product_id),
        )
        pg_conn.execute(
            """
            UPDATE inventory
            SET quantity_on_hand = %s, quantity_reserved = 0, updated_at = now()
            WHERE product_id = %s
              AND product_variant_id IS NULL
              AND location_code = 'default'
            """,
            (row["stock"], product_id),
        )

    return len(rows)


def migrate_orders(pg_conn, sqlite_path: Path, product_id_map: dict[int, str]) -> tuple[dict[str, str], int]:
    order_id_map = {}
    rows = sqlite_rows(
        sqlite_path,
        """
        SELECT
            o.id,
            o.customer_name,
            o.product_id,
            o.quantity,
            o.total_price,
            o.status,
            o.shipping_address,
            o.order_date,
            o.estimated_arrival,
            p.name AS product_name
        FROM orders o
        JOIN products p ON p.id = o.product_id
        ORDER BY o.id
        """,
    )

    for row in rows:
        status = ORDER_STATUS_MAP.get(row["status"], "processing")
        user_id, customer_email = ensure_demo_user(pg_conn, row["customer_name"])
        result = pg_conn.execute(
            """
            INSERT INTO orders (
                order_number, user_id, customer_name, customer_email, status, shipping_address, subtotal,
                grand_total, currency, order_date, estimated_arrival, metadata
            )
            VALUES (%s, %s, %s, %s, %s::order_status, %s, %s, %s, 'IDR', %s, %s, %s::jsonb)
            ON CONFLICT (order_number) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                customer_name = EXCLUDED.customer_name,
                customer_email = EXCLUDED.customer_email,
                status = EXCLUDED.status,
                shipping_address = EXCLUDED.shipping_address,
                subtotal = EXCLUDED.subtotal,
                grand_total = EXCLUDED.grand_total,
                order_date = EXCLUDED.order_date,
                estimated_arrival = EXCLUDED.estimated_arrival,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING id
            """,
            (
                row["id"],
                user_id,
                row["customer_name"],
                customer_email,
                status,
                row["shipping_address"],
                row["total_price"],
                row["total_price"],
                row["order_date"],
                row["estimated_arrival"],
                json.dumps({"source": "sqlite", "sqlite_order_id": row["id"]}),
            ),
        ).fetchone()
        order_uuid = result[0]
        order_id_map[row["id"]] = order_uuid

        product_id = product_id_map[row["product_id"]]
        unit_price = row["total_price"] / row["quantity"] if row["quantity"] else row["total_price"]
        pg_conn.execute("DELETE FROM order_items WHERE order_id = %s", (order_uuid,))
        pg_conn.execute(
            """
            INSERT INTO order_items (
                order_id, product_id, product_name, sku, quantity, unit_price, line_total, currency
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'IDR')
            """,
            (
                order_uuid,
                product_id,
                row["product_name"],
                f"SQLITE-PROD-{row['product_id']:04d}",
                row["quantity"],
                unit_price,
                row["total_price"],
            ),
        )

    return order_id_map, len(rows)


def migrate_cart(pg_conn, sqlite_path: Path, product_id_map: dict[int, str]) -> tuple[int, int]:
    rows = sqlite_rows(
        sqlite_path,
        """
        SELECT
            c.id,
            c.session_id,
            c.product_id,
            c.quantity,
            c.added_at,
            p.price
        FROM shopping_cart c
        JOIN products p ON p.id = c.product_id
        ORDER BY c.id
        """,
    )

    cart_id_map = {}
    for row in rows:
        session_id = row["session_id"] or "default"
        if session_id not in cart_id_map:
            result = pg_conn.execute(
                """
                INSERT INTO shopping_carts (session_id, currency, metadata)
                VALUES (%s, 'IDR', %s::jsonb)
                ON CONFLICT (session_id) DO UPDATE SET updated_at = now()
                RETURNING id
                """,
                (session_id, json.dumps({"source": "sqlite"})),
            ).fetchone()
            cart_id_map[session_id] = result[0]

        cart_id = cart_id_map[session_id]
        product_id = product_id_map[row["product_id"]]
        pg_conn.execute(
            """
            DELETE FROM shopping_cart_items
            WHERE shopping_cart_id = %s
              AND product_id = %s
              AND product_variant_id IS NULL
            """,
            (cart_id, product_id),
        )
        pg_conn.execute(
            """
            INSERT INTO shopping_cart_items (
                shopping_cart_id, product_id, product_variant_id, quantity, unit_price, currency, added_at
            )
            VALUES (%s, %s, NULL, %s, %s, 'IDR', %s)
            """,
            (cart_id, product_id, row["quantity"], row["price"], row["added_at"]),
        )

    return len(cart_id_map), len(rows)


def migrate_support(pg_conn, sqlite_path: Path) -> int:
    rows = sqlite_rows(
        sqlite_path,
        """
        SELECT id, customer_message, agent_summary, priority, status, created_at
        FROM support_tickets
        ORDER BY id
        """,
    )

    for row in rows:
        ticket_number = f"SQLITE-TICKET-{row['id']:04d}"
        pg_conn.execute(
            """
            INSERT INTO support_tickets (
                ticket_number, customer_message, agent_summary, priority, status, created_at
            )
            VALUES (%s, %s, %s, %s::support_ticket_priority, %s::support_ticket_status, %s)
            ON CONFLICT (ticket_number) DO UPDATE SET
                customer_message = EXCLUDED.customer_message,
                agent_summary = EXCLUDED.agent_summary,
                priority = EXCLUDED.priority,
                status = EXCLUDED.status,
                updated_at = now()
            """,
            (
                ticket_number,
                row["customer_message"],
                row["agent_summary"],
                TICKET_PRIORITY_MAP.get(row["priority"], "normal"),
                TICKET_STATUS_MAP.get(row["status"], "open"),
                row["created_at"],
            ),
        )

    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate SQLite store data to PostgreSQL.")
    parser.add_argument("--sqlite-path", default=str(get_settings().database_path))
    parser.add_argument("--database-url", default=get_settings().postgres_database_url)
    parser.add_argument("--apply-schema", action="store_true")
    parser.add_argument("--clear-target", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        print(f"SQLite database not found: {sqlite_path}", file=sys.stderr)
        return 1

    if not args.database_url:
        print("DATABASE_URL is required. Set it in .env.secrets or pass --database-url.", file=sys.stderr)
        return 1

    products = sqlite_rows(sqlite_path, "SELECT COUNT(*) AS count FROM products")[0]["count"]
    orders = sqlite_rows(sqlite_path, "SELECT COUNT(*) AS count FROM orders")[0]["count"]
    cart_items = sqlite_rows(sqlite_path, "SELECT COUNT(*) AS count FROM shopping_cart")[0]["count"]
    support_tickets = sqlite_rows(sqlite_path, "SELECT COUNT(*) AS count FROM support_tickets")[0]["count"]

    if args.dry_run:
        print("SQLite -> PostgreSQL migration dry run")
        print(f"products: {products}")
        print(f"inventory: {products}")
        print(f"orders: {orders}")
        print(f"cart items: {cart_items}")
        print(f"support tickets: {support_tickets}")
        return 0

    psycopg = import_psycopg()
    with psycopg.connect(args.database_url) as pg_conn:
        with pg_conn.transaction():
            if args.apply_schema:
                apply_schema(pg_conn)
            if args.clear_target:
                clear_target(pg_conn)

            product_id_map = migrate_products(pg_conn, sqlite_path)
            inventory_count = migrate_inventory(pg_conn, sqlite_path, product_id_map)
            _, order_count = migrate_orders(pg_conn, sqlite_path, product_id_map)
            cart_count, cart_item_count = migrate_cart(pg_conn, sqlite_path, product_id_map)
            support_count = migrate_support(pg_conn, sqlite_path)

            pg_conn.execute(
                """
                INSERT INTO schema_migrations (version, description)
                VALUES ('DATA_SQLITE_001', 'migrated SQLite data to PostgreSQL')
                ON CONFLICT (version) DO UPDATE SET applied_at = now()
                """
            )

    print("SQLite -> PostgreSQL migration complete.")
    print(f"products: {len(product_id_map)}")
    print(f"inventory: {inventory_count}")
    print(f"orders: {order_count}")
    print(f"shopping carts: {cart_count}")
    print(f"shopping cart items: {cart_item_count}")
    print(f"support tickets: {support_count}")
    print(f"finished_at: {datetime.now().isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
