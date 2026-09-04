#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DUMP_FILE="${1:-}"
SCRATCH_DB="${RESTORE_TEST_DB:-ai_agent_restore_test}"
REQUIRE_ROWS_TABLES="${REQUIRE_ROWS_TABLES:-products orders users}"
REQUIRE_EXISTS_TABLES="${REQUIRE_EXISTS_TABLES:-conversations messages document_chunks llm_requests request_traces trace_spans resource_usage_events tenant_ai_budgets}"
PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-}"

if [ -z "$PGPASSWORD" ] && [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
  PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
fi
if [ -z "$PGPASSWORD" ]; then
  echo "[restore-test] PGPASSWORD is required (set PGPASSWORD or POSTGRES_PASSWORD_FILE)" >&2
  exit 3
fi
export PGPASSWORD

if [ -z "$DUMP_FILE" ]; then
  DUMP_FILE="$(ls -t "$BACKUP_DIR"/${PGDATABASE:-ai_agent}_*.dump 2>/dev/null | head -1 || true)"
fi

if [ -z "$DUMP_FILE" ] || [ ! -f "$DUMP_FILE" ]; then
  echo "[restore-test] FAIL: no dump file found in $BACKUP_DIR" >&2
  exit 2
fi

echo "[restore-test] restoring $DUMP_FILE into scratch DB '$SCRATCH_DB'"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$SCRATCH_DB\";" >/dev/null
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$SCRATCH_DB\";" >/dev/null
pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$SCRATCH_DB" --no-owner --no-privileges -Fc "$DUMP_FILE"

FAIL=0

for table in $REQUIRE_ROWS_TABLES; do
  count="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$SCRATCH_DB" -tAc "SELECT count(*) FROM \"$table\";" 2>/dev/null || true)"
  if [ -z "$count" ] || [ "$count" -le 0 ] 2>/dev/null; then
    echo "[restore-test] FAIL: table $table has no rows"
    FAIL=1
  else
    echo "[restore-test] OK: $table rows=$count"
  fi
done

for table in $REQUIRE_EXISTS_TABLES; do
  exists="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$SCRATCH_DB" -tAc "SELECT to_regclass('public.$table') IS NOT NULL;" 2>/dev/null || true)"
  if [ "$exists" != "t" ]; then
    echo "[restore-test] FAIL: table $table missing"
    FAIL=1
  else
    echo "[restore-test] OK: table $table exists"
  fi
done

migration_count="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$SCRATCH_DB" -tAc "SELECT count(*) FROM schema_migrations;" 2>/dev/null || true)"
latest_migration="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$SCRATCH_DB" -tAc "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1;" 2>/dev/null || true)"
if [ -z "$migration_count" ] || [ "$migration_count" -le 0 ] 2>/dev/null || ! [[ "$latest_migration" == V02* ]]; then
  echo "[restore-test] FAIL: schema_migrations incomplete (count=$migration_count latest=$latest_migration)"
  FAIL=1
else
  echo "[restore-test] OK: schema_migrations count=$migration_count latest=$latest_migration"
fi

vector_present="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$SCRATCH_DB" -tAc "SELECT count(*) FROM pg_extension WHERE extname='vector';" 2>/dev/null || true)"
if [ "$vector_present" != "1" ]; then
  echo "[restore-test] FAIL: vector extension missing"
  FAIL=1
else
  echo "[restore-test] OK: vector extension present"
fi

psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$SCRATCH_DB\";" >/dev/null

if [ "$FAIL" = "0" ]; then
  echo "[restore-test] PASS"
  exit 0
fi
echo "[restore-test] FAIL"
exit 1