#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DUMP_FILE="${1:-}"
TARGET_DB="${TARGET_DB:-ai_agent}"
DROP_TARGET="${DROP_TARGET:-false}"
CREATE_TARGET="${CREATE_TARGET:-true}"
PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-}"

if [ -z "$PGPASSWORD" ] && [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
  PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
fi
if [ -z "$PGPASSWORD" ]; then
  echo "[restore] PGPASSWORD is required (set PGPASSWORD or POSTGRES_PASSWORD_FILE)" >&2
  exit 3
fi
export PGPASSWORD

if [ -z "$DUMP_FILE" ]; then
  DUMP_FILE="$(ls -t "$BACKUP_DIR"/${PGDATABASE:-ai_agent}_*.dump 2>/dev/null | head -1 || true)"
fi

if [ -z "$DUMP_FILE" ] || [ ! -f "$DUMP_FILE" ]; then
  echo "[restore] no dump file found (use: restore_postgres.sh <dump-file>)" >&2
  exit 2
fi

if [ "$DROP_TARGET" = "true" ]; then
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS \"$TARGET_DB\";"
fi

if [ "$CREATE_TARGET" = "true" ]; then
  psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -c "CREATE DATABASE \"$TARGET_DB\";"
fi

pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" --no-owner --no-privileges -Fc "$DUMP_FILE"

echo "[restore] restored $DUMP_FILE into $TARGET_DB"