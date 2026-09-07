#!/bin/sh
set -eu

# Docker Compose mounts secrets root-owned (often 0400). The backend runs the
# runtime process as a non-root user, so make the secret files world-readable
# first. This entrypoint runs as root; uvicorn is then dropped to uid 1000.
if [ -d /run/secrets ]; then
  chmod 0644 /run/secrets/* 2>/dev/null || true
fi

if [ "${DATABASE_PROVIDER:-postgres}" = "postgres" ] && [ "${RUN_DATABASE_MIGRATIONS:-true}" = "true" ]; then
  python database/migrate_sqlite_to_postgres.py --schema-only
fi

exec setpriv --reuid=1000 --regid=1000 --init-groups "$@"