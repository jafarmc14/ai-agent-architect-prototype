"""Enable login for an existing seeded order owner in development/testing."""
import argparse
from getpass import getpass
import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402
from core.auth.password import hash_password  # noqa: E402


def find_accounts(conn, order_id: str, admin_email: str):
    admin = conn.execute("""SELECT id FROM users WHERE tenant_id = 'default'
        AND lower(email) = lower(%s) AND metadata->>'role' = 'admin'
        AND password_hash IS NOT NULL""", (admin_email,)).fetchone()
    if not admin:
        raise ValueError("An active admin login in the default tenant is required")
    owner = conn.execute("""SELECT u.id, u.name, u.email, o.order_number, o.status::text AS status
        FROM orders o JOIN users u ON u.id = o.user_id AND u.tenant_id = o.tenant_id
        WHERE o.tenant_id = 'default' AND upper(o.order_number) = upper(%s)
          AND u.metadata->>'source' = 'demo_seed'
          AND coalesce(u.metadata->>'role', 'customer') = 'customer'""", (order_id,)).fetchone()
    if not owner:
        raise ValueError("Order must belong to an existing seeded demo customer")
    if owner["status"] not in {"awaiting_payment", "processing"}:
        raise ValueError("Choose a demo order with Awaiting Payment or Processing status")
    if owner["id"] == admin["id"]:
        raise ValueError("Customer and admin must be different accounts")
    return owner


def activate(conn, owner, password: str):
    if len(password) < 12:
        raise ValueError("Customer password must have at least 12 characters")
    conn.execute("""UPDATE users SET password_hash = %s,
        metadata = metadata || '{"role":"customer"}'::jsonb, updated_at = now()
        WHERE id = %s AND tenant_id = 'default'""",
        (hash_password(password), owner["id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate login for a seeded demo customer who owns an active order")
    parser.add_argument("--order-id", default="ORD005")
    parser.add_argument("--admin-email", default="admin@example.local")
    parser.add_argument("--generate-password", action="store_true",
                        help="Write a generated customer password to an ignored local .secrets file")
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env not in {"development", "testing"} or settings.database_provider != "postgres":
        parser.error("This command requires a development/testing PostgreSQL environment")

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(settings.postgres_database_url, row_factory=dict_row) as conn:
        owner = find_accounts(conn, args.order_id, args.admin_email)
        print(f"Customer: {owner['name']} <{owner['email']}>; order: {owner['order_number']} ({owner['status']})")
        if args.generate_password:
            password = secrets.token_urlsafe(24)
        else:
            password = getpass("New customer password (at least 12 characters): ")
            if password != getpass("Confirm customer password: "):
                raise ValueError("Passwords do not match")
        activate(conn, owner, password)
    if args.generate_password:
        secret_dir = PROJECT_ROOT / ".secrets"
        secret_dir.mkdir(mode=0o700, exist_ok=True)
        credential_file = secret_dir / "demo_customer_login.txt"
        credential_file.write_text(f"Email: {owner['email']}\nPassword: {password}\n", encoding="utf-8")
        credential_file.chmod(0o600)
        print(f"Credentials saved locally: {credential_file}")
    print(f"Customer login activated for {owner['email']}. Admin account unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
