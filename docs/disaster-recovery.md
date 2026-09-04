# Disaster Recovery

This document defines the backup and disaster recovery (DR) posture for the AI-Agent prototype's primary datastore: the PostgreSQL database (`ai_agent`) running in the `postgres` container.

## Scope

| Item | In scope | Notes |
|---|---|---|
| PostgreSQL `ai_agent` DB | Yes | All runtime data: products, inventory, orders, cart, support, conversations, users, `llm_requests`, observability traces, resource usage, `document_chunks` (pgvector), `schema_migrations` ledger |
| Redis | No | Provisioned in the stacks but not consumed by the application yet |
| SQLite `toko.db` | No | Legacy migration source only, gitignored |
| LLM / embedding providers | No | Stateless; recovered by normal provider credentials |

## Recovery Objectives

| Objective | Target | Rationale |
|---|---|---|
| **RPO** (Recovery Point Objective) | ≤ 24 hours | A full logical backup is taken once per day; worst case we lose up to one day of writes |
| **RTO** (Recovery Time Objective) | ≤ 30 minutes | Restore the latest dump into a fresh/cleaned database, run the idempotent entrypoint migrations, and verify the schema and key tables |

> Lowering RPO to minutes would require WAL archiving / `pg_basebackup` / replication. That is intentionally out of scope for this prototype scale; revisit when the deployment needs continuous data protection.

## Backup Policy

| Setting | Value | Source |
|---|---|---|
| Format | `pg_dump -Fc` (custom, compressed) | `scripts/backup_postgres.sh` |
| Schedule | Daily (one-shot; host scheduler or `docker compose run`) | See "Running a Backup" |
| Retention | 14 days, rolling (oldest deleted first) | `BACKUP_RETENTION_DAYS` (default `14`) |
| Location | Dedicated backup volume (`ai_agent_postgres_dev_backups` in dev) or a host directory | `BACKUP_DIR` |
| Naming | `<db>_YYYYmmdd_HHMMSS.dump` + matching `.manifest.json` | `backup_postgres.sh` |

Retention of 14 days covers at least two full RPO cycles with margin. Backups are logical dumps and are portable across PostgreSQL versions compatible with `pg_restore`.

### Recommended off-site copy

For any long-lived deployment, copy the newest dump off the host after each backup (object storage, another host, or a scheduled `scp`/`rclone`). The script only manages local retention; off-site transfer is left to the host scheduler.

## Running a Backup

All scripts are environment-driven via standard `PG*` variables (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) plus `BACKUP_DIR` and `BACKUP_RETENTION_DAYS`.

### Development (one-shot via the dev compose backup service)

```powershell
docker compose -f docker-compose.dev.yml --profile backup run --rm db-backup
```

This starts the Postgres image, runs `scripts/backup_postgres.sh` against the `postgres` service, writes the dump to the `ai_agent_postgres_dev_backups` volume, then exits.

### Any environment (direct)

```bash
PGHOST=postgres PGPORT=5432 PGUSER=postgres PGPASSWORD=<secret> PGDATABASE=ai_agent \
BACKUP_DIR=/backups BACKUP_RETENTION_DAYS=14 \
  /scripts/backup_postgres.sh
```

### Host scheduling (recommended for deployment, keeps the stack lean)

Production keeps the compose stack unchanged. Schedule the same script with a host cron entry (Linux) or Task Scheduler (Windows):

```bash
# crontab -e  (example: daily at 02:00)
0 2 * * * cd /path/to/project && docker compose -f docker-compose.prod.yml exec -T postgres bash -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /backups/dump_$(date +\%Y\%m\%d_\%H\%M\%S).dump' 
```

> Use a dedicated backup service or host directory that survives container recreation. A backup written only to a Postgres container's filesystem is lost when the container is replaced.

## Restore Procedure

### Restore a dump into a target database

```bash
TARGET_DB=ai_agent DROP_TARGET=true CREATE_TARGET=true \
  /scripts/restore_postgres.sh /backups/ai_agent_20260905_020000.dump
```

After restore, start the application stack. The backend entrypoint runs `migrate_sqlite_to_postgres.py --schema-only`, which is idempotent: versions already present in the restored `schema_migrations` ledger are skipped.

### DR runbook

| Scenario | Steps |
|---|---|
| **Single corrupt/missing table** | Restore the full DB into a scratch database, extract the missing table with `pg_dump -t <table>`, and re-import it. |
| **Whole DB corruption** | Stop backend → run `DROP_TARGET=true` restore of the latest dump → start backend (entrypoint migrations are idempotent) → verify with the restore test. |
| **Postgres volume lost** | Start a fresh `postgres` container (new volume) → restore the latest dump → start backend → verify. |
| **Host / container loss** | Rebuild the stack (`docker compose up -d`), restore the latest dump from the backup location, apply off-site dump if the host backup was lost, then verify. |
| **Full environment rebuild** | Provision host, checkout repo, create secrets, start Postgres, restore latest dump, start stack, run ingest/embed scripts only if derived data needs refresh (they are idempotent upserts). |

## Restore Verification (Mandatory)

"Backup without a restore test is not a backup." The automated restore test must pass after every real backup and after any retention/configuration change.

`scripts/test_backup_restore.sh`:
1. Restores the latest (or an explicit) dump into a scratch DB `ai_agent_restore_test`.
2. Asserts non-empty row counts for the seeded tables `products`, `orders`, and `users`.
3. Asserts the runtime tables exist (`conversations`, `messages`, `document_chunks`, `llm_requests`, `request_traces`, `trace_spans`, `resource_usage_events`, `tenant_ai_budgets`).
4. Asserts `schema_migrations` is populated with the latest applied version.
5. Asserts the `vector` extension is present.
6. Drops the scratch DB and exits 0 on success, 1 on failure.

```bash
# Dev (via the backup service)
docker compose -f docker-compose.dev.yml --profile backup run --rm db-backup /scripts/test_backup_restore.sh
```

CI runs this automatically on every pull request: the `integration` job backs up the migrated Postgres fixture and runs the restore test (see `.github/workflows/ci-quality-gate.yml`).

## Testing Cadence

| When | Action |
|---|---|
| Every pull request | CI `integration` job runs backup + restore test |
| After each manual backup | Run `test_backup_restore.sh` |
| On any change to retention, restore, or backup scripts | Run the restore test |
| Recommended | A quarterly full restore into a fresh host, timed to confirm the RTO target |

## Ownership

- Backup execution and off-site copy: the operator responsible for the deployment.
- Restore procedure and DR runbook: maintained in this document; changes require a passing restore test.