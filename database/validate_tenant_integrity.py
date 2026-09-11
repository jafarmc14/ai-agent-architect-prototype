"""Operator historical-FK validation. Does not repair or move tenant data."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg import sql
from core.repositories.postgres_connection import get_postgres_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="Validate all historical tenant references atomically")
    args = parser.parse_args()
    with get_postgres_connection() as conn:
        rows = conn.execute("""SELECT c.conname, r.relname FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE n.nspname = 'public' AND c.conname LIKE 'tenant_fk_%%' AND NOT c.convalidated
            ORDER BY r.relname, c.conname""").fetchall()
        if args.validate:
            for row in rows:
                try:
                    conn.execute(sql.SQL("ALTER TABLE public.{} VALIDATE CONSTRAINT {}").format(
                        sql.Identifier(row["relname"]), sql.Identifier(row["conname"])))
                except Exception:
                    conn.rollback()
                    print(json.dumps({"valid": False, "table": row["relname"], "constraint": row["conname"],
                                      "action": "Review tenant assignments before deploying; no data was repaired."}))
                    return 1
        print(json.dumps({"validated": len(rows) if args.validate else 0,
                          "pending": [] if args.validate else rows, "data_modified": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
