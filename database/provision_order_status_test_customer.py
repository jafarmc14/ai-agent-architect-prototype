"""Provision a development customer with shipped and completed test orders."""
import sys
from getpass import getpass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402
from core.auth.password import hash_password  # noqa: E402


EMAIL = "status.test@example.local"
NAME = "Order Status Test Customer"
ORDERS = (("ORD009", "shipped"), ("ORD010", "completed"))
LEGACY_ORDER_NUMBERS = {"ORD009": "TEST-SHIPPED-001", "ORD010": "TEST-COMPLETED-001"}


def provision(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Test customer password must have at least 12 characters")
    settings = get_settings()
    if settings.app_env not in {"development", "testing"} or settings.database_provider != "postgres":
        raise ValueError("This fixture requires a development/testing PostgreSQL environment")

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(settings.postgres_database_url, row_factory=dict_row) as conn:
        user = conn.execute("""SELECT id, metadata FROM users
            WHERE tenant_id = 'default' AND lower(email) = %s""", (EMAIL,)).fetchone()
        if user and user["metadata"].get("source") != "demo_status_fixture":
            raise ValueError("The test email already belongs to a different account")
        if user:
            user_id = user["id"]
            conn.execute("""UPDATE users SET password_hash = %s, updated_at = now()
                WHERE id = %s AND tenant_id = 'default'""", (hash_password(password), user_id))
        else:
            user_id = conn.execute("""INSERT INTO users
                (tenant_id, name, email, password_hash, metadata)
                VALUES ('default', %s, %s, %s,
                    '{"role":"customer","source":"demo_status_fixture"}'::jsonb)
                RETURNING id""", (NAME, EMAIL, hash_password(password))).fetchone()["id"]

        for order_number, status in ORDERS:
            order = conn.execute("""SELECT id, user_id, status::text AS status FROM orders
                WHERE tenant_id = 'default' AND order_number = %s""", (order_number,)).fetchone()
            if not order:
                legacy = conn.execute("""SELECT id, user_id, status::text AS status, metadata
                    FROM orders WHERE tenant_id = 'default' AND order_number = %s""",
                    (LEGACY_ORDER_NUMBERS[order_number],)).fetchone()
                if legacy:
                    if (legacy["user_id"] != user_id or legacy["status"] != status
                            or legacy["metadata"].get("source") != "demo_status_fixture"):
                        raise ValueError("Legacy test order does not belong to this fixture")
                    conn.execute("UPDATE orders SET order_number = %s WHERE id = %s", (order_number, legacy["id"]))
                    order = legacy
            if order and (order["user_id"] != user_id or order["status"] != status):
                raise ValueError(f"Order number {order_number} is already used by a different fixture")
            if not order:
                order = conn.execute("""INSERT INTO orders
                    (tenant_id, order_number, user_id, customer_name, customer_email,
                     status, shipping_address, subtotal, grand_total, currency, metadata)
                    VALUES ('default', %s, %s, %s, %s, %s::order_status,
                            'Demo shipping address', 100000, 100000, 'IDR',
                            '{"source":"demo_status_fixture"}'::jsonb)
                    RETURNING id""", (order_number, user_id, NAME, EMAIL, status)).fetchone()
            conn.execute("""INSERT INTO order_items
                (tenant_id, order_id, product_name, quantity, unit_price, line_total, currency)
                SELECT 'default', %s, 'Demo status test item', 1, 100000, 100000, 'IDR'
                WHERE NOT EXISTS (SELECT 1 FROM order_items WHERE tenant_id = 'default' AND order_id = %s)""",
                (order["id"], order["id"]))


def main() -> int:
    password = getpass("Test customer password (at least 12 characters): ")
    if password != getpass("Confirm password: "):
        raise ValueError("Passwords do not match")
    provision(password)
    print(f"Test customer ready: {EMAIL}")
    for order_number, status in ORDERS:
        print(f"{order_number}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
