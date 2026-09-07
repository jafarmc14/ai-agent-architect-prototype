#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DUMP_FILE="${1:-}"
SCRATCH_DB="${RESTORE_TEST_DB:-ai_agent_restore_test}"
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

# Data preservation: compare the restored row counts against the counts the
# backup recorded in its manifest at backup time. This validates the backup
# regardless of whether the source is empty (fresh deployment) or fully seeded,
# and is immune to writes that happen on the live source after the backup.
MANIFEST_FILE="${DUMP_FILE%.dump}.manifest.json"
if [ ! -f "$MANIFEST_FILE" ]; then
  echo "[restore-test] FAIL: manifest not found next to dump: $MANIFEST_FILE"
  exit 2
fi

count_checked=0
while IFS= read -r line; do
  table="$(printf '%s\n' "$line" | sed -n 's/^[[:space:]]*"\([^"]*\)"[[:space:]]*:[[:space:]]*\([0-9]*\)[[:space:]]*,*$/\1/p')"
  expected="$(printf '%s\n' "$line" | sed -n 's/^[[:space:]]*"\([^"]*\)"[[:space:]]*:[[:space:]]*\([0-9]*\)[[:space:]]*,*$/\2/p')"
  if [ -z "$table" ] || [ -z "$expected" ]; then
    continue
  fi
  restored="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$SCRATCH_DB" -tAc "SELECT count(*) FROM \"$table\";" 2>/dev/null || true)"
  count_checked=$((count_checked + 1))
  if [ -z "$restored" ]; then
    echo "[restore-test] FAIL: table $table missing in restored DB"
    FAIL=1
  elif [ "$restored" != "$expected" ]; then
    echo "[restore-test] FAIL: $table row count mismatch (backup=$expected restored=$restored)"
    FAIL=1
  else
    echo "[restore-test] OK: $table rows=$restored (matches backup)"
  fi
done < <(awk '/"table_counts": \{/{in_block=1; next} in_block && /^  \}/{exit} in_block{print}' "$MANIFEST_FILE")

if [ "$count_checked" -eq 0 ]; then
  echo "[restore-test] WARN: no table counts found in manifest"
fi

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