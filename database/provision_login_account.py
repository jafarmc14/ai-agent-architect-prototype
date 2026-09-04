import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth.password import hash_password  # noqa: E402
from configs import get_settings  # noqa: E402

DEFAULT_EMAIL = "admin@example.local"
DEFAULT_PASSWORD = "Admin@2026!"


def provision(email: str, password: str, name: str, role: str, tenant_id: str) -> str:
    import psycopg

    settings = get_settings()
    if settings.database_provider != "postgres":
        print("Provisioning a login account requires DATABASE_PROVIDER=postgres.", file=sys.stderr)
        raise SystemExit(2)
    password_hash = hash_password(password)
    metadata = json.dumps({"role": role, "tenant_id": tenant_id})
    with psycopg.connect(settings.postgres_database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (email, name, password_hash, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE
                SET name = EXCLUDED.name,
                    password_hash = EXCLUDED.password_hash,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                RETURNING id
                """,
                (email, name, password_hash, metadata),
            )
            user_id = cursor.fetchone()[0]
    return str(user_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision or update a login account for the frontend login gate.")
    parser.add_argument("--email", default=None, help="Login username (email). Defaults to LOGIN_USERNAME or admin@example.local")
    parser.add_argument("--password", default=None, help="Login password. Defaults to LOGIN_PASSWORD or Admin@2026!")
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--role", default="admin", choices=["customer", "support_agent", "manager", "admin"])
    parser.add_argument("--tenant-id", default="default")
    args = parser.parse_args()

    import os

    email = args.email or os.getenv("LOGIN_USERNAME") or DEFAULT_EMAIL
    password = args.password or os.getenv("LOGIN_PASSWORD") or DEFAULT_PASSWORD

    user_id = provision(email.lower().strip(), password, args.name, args.role, args.tenant_id)
    print(f"Login account provisioned: {email.lower().strip()} (id={user_id}, role={args.role})")
    print("Use these credentials on the login page. Store them securely and rotate via --password if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())