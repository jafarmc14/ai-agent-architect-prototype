#!/bin/sh
set -eu

# Docker Compose mounts secrets under /run/secrets read-only, often 0400, so a
# non-root runtime user cannot read them (chmod on the mount is not permitted).
# Copy them to a writable runtime dir and make them world-readable, then point
# the app at that dir via SECRET_DIR. This entrypoint runs as root; the final
# process is dropped to uid 1000 via setpriv.
if [ -d /run/secrets ] && [ -z "${SECRET_DIR:-}" ]; then
  mkdir -p /run/secrets-runtime
  for secret_file in /run/secrets/*; do
    [ -f "$secret_file" ] || continue
    base_name=$(basename "$secret_file")
    cp "$secret_file" "/run/secrets-runtime/$base_name"
    chmod 0644 "/run/secrets-runtime/$base_name"
  done
  export SECRET_DIR=/run/secrets-runtime
fi

if [ "${DATABASE_PROVIDER:-postgres}" = "postgres" ] && [ "${RUN_DATABASE_MIGRATIONS:-true}" = "true" ]; then
  python database/migrate_sqlite_to_postgres.py --schema-only
fi

exec setpriv --reuid=1000 --regid=1000 --init-groups "$@"