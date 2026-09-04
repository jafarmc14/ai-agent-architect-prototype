#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
DB_NAME="${PGDATABASE:-ai_agent}"
PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-}"

if [ -z "$PGPASSWORD" ] && [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
  PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
fi
if [ -z "$PGPASSWORD" ]; then
  echo "[backup] PGPASSWORD is required (set PGPASSWORD or POSTGRES_PASSWORD_FILE)" >&2
  exit 3
fi
export PGPASSWORD

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/${DB_NAME}_${STAMP}.dump"
MANIFEST_FILE="$BACKUP_DIR/${DB_NAME}_${STAMP}.manifest.json"

pg_dump -Fc -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$DB_NAME" -f "$DUMP_FILE"

if command -v stat >/dev/null 2>&1; then
  SIZE_BYTES="$(stat -c %s "$DUMP_FILE" 2>/dev/null || stat -f %z "$DUMP_FILE")"
else
  SIZE_BYTES="$(wc -c < "$DUMP_FILE")"
fi

cat > "$MANIFEST_FILE" <<EOF
{
  "database": "$DB_NAME",
  "dump_file": "$DUMP_FILE",
  "size_bytes": $SIZE_BYTES,
  "format": "pg_dump custom",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "retention_days": $RETENTION_DAYS
}
EOF

find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -type f -mtime +"$RETENTION_DAYS" -delete

echo "[backup] created $DUMP_FILE ($SIZE_BYTES bytes), retention=${RETENTION_DAYS}d"