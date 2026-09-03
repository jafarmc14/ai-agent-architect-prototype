#!/bin/sh
set -eu

if [ "${DATABASE_PROVIDER:-postgres}" = "postgres" ] && [ "${RUN_DATABASE_MIGRATIONS:-true}" = "true" ]; then
  python database/migrate_sqlite_to_postgres.py --schema-only
fi

exec "$@"
