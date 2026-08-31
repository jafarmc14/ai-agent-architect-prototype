# Database Migrations

This folder contains versioned database migration files.

## Structure

```text
database/migrations/
└── postgres/
    └── V001__initial_schema.sql
    └── V002__enable_pgvector_document_chunks.sql
```

## Naming Convention

Use this pattern:

```text
V<version>__<description>.sql
```

Examples:

```text
V001__initial_schema.sql
V002__enable_pgvector_document_chunks.sql
V003__add_operational_indexes.sql
```

Rules:

- Increase the version number monotonically.
- Do not edit migrations that have already been applied to shared/staging/production databases.
- Add a new migration for every schema change.
- Keep secrets out of migration files.

## Manual Apply

Apply migrations in version order:

```bash
psql "$DATABASE_URL" -f database/migrations/postgres/V001__initial_schema.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V002__enable_pgvector_document_chunks.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V003__add_operational_indexes.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V004__add_product_embeddings.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V005__use_ollama_embedding_dimensions.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V006__add_product_keyword_search_index.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V007__add_document_freshness_fields.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V008__add_document_approval_status.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V009__seed_demo_users_and_bind_orders.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V010__add_write_controls_and_audit_logs.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V011__upgrade_support_escalations.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V012__add_conversation_structured_state.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V013__add_prompt_versioning.sql
psql "$DATABASE_URL" -f database/migrations/postgres/V014__add_model_version_governance.sql
```

`V001__initial_schema.sql` creates a `schema_migrations` table and records itself after successful execution. Later migrations should insert their own version into `schema_migrations` at the end of the file.

`V003__add_operational_indexes.sql` adds tenant-aware lookup columns and operational indexes for SKU, category, tenant, user, order, document metadata, and vector search access patterns.

`V004__add_product_embeddings.sql` adds pgvector-backed product embedding storage. Product embeddings must be generated from relevant semantic fields only, excluding factual filter fields such as price, stock, SKU, IDs, currency, and timestamps.

`V005__use_ollama_embedding_dimensions.sql` changes product and document vector columns to `vector(768)`, aligned with Ollama `nomic-embed-text`.

`V006__add_product_keyword_search_index.sql` adds a PostgreSQL GIN full-text index for the keyword side of hybrid product search.

`V007__add_document_freshness_fields.sql` adds document freshness columns: `effective_date`, `expires_at`, `status`, and `superseded_by`.

`V008__add_document_approval_status.sql` adds the document approval lifecycle column used by secure knowledge ingestion: `uploaded`, `reviewed`, `approved`, and `indexed`.

`V009__seed_demo_users_and_bind_orders.sql` creates demo customer identities from migrated orders and binds `orders.user_id` for authenticated request-context filtering.

`V010__add_write_controls_and_audit_logs.sql` adds idempotency records and audit logs for controlled write actions.

`V011__upgrade_support_escalations.sql` adds escalation metadata to support tickets.

`V012__add_conversation_structured_state.sql` adds compact structured conversation state and message ordering indexes for multi-turn continuity.

`V013__add_prompt_versioning.sql` adds prompt version metadata storage and prompt version columns on LLM request logs.

`V014__add_model_version_governance.sql` adds provider/model/model_version observability columns on LLM request logs.

## Vector Storage

`V002__enable_pgvector_document_chunks.sql` enables the `vector` extension and adds pgvector-backed storage to `document_chunks`:

```text
embedding_vector vector(768)
embedding_model
embedding_dimensions
```

The migration also creates an `ivfflat` cosine index for approximate nearest-neighbor search. PostgreSQL must have the pgvector extension installed before applying `V002`.

## Operational Indexes

`V003__add_operational_indexes.sql` covers the Phase 5 index baseline:

```text
SKU lookup
category lookup
tenant_id filtering
user_id joins and filters
order_id joins and filters
document metadata JSONB search
document freshness filtering
document approval filtering
document chunk vector search
product vector search
product keyword search
```

## Current Runtime

The application runtime can use SQLite or PostgreSQL through `DATABASE_PROVIDER`. The current PostgreSQL path is ready for product, order, cart, support, conversation state, prompt version metadata, model version governance, document vector, product embedding, and hybrid product search workflows.

## SQLite to PostgreSQL Data Migration

The data migration script is:

```text
database/migrate_sqlite_to_postgres.py
```

It migrates data in this order:

```text
products
inventory
orders
cart
support
```

Install the PostgreSQL driver:

```bash
py -m pip install psycopg[binary]
```

Start the project PostgreSQL container:

```bash
docker compose -f docker-compose.postgres.yml up -d
```

The project container maps host port `5435` to PostgreSQL's internal port `5432`, so it can run alongside other local PostgreSQL containers that already use `5433` or `5434`.

Set `DATABASE_URL` in `.env.secrets` or `.env`:

```bash
DATABASE_URL=postgresql://postgres:password@localhost:5435/ai_agent
POSTGRES_PASSWORD=password
```

Docker Compose reads `POSTGRES_PASSWORD` from `.env` automatically. If the variable is not set, the local compose file uses `password` as the development default.

Check the port before running migrations:

```bash
Test-NetConnection localhost -Port 5435
```

Preview source counts without writing to PostgreSQL:

```bash
py database/migrate_sqlite_to_postgres.py --dry-run
```

Apply all versioned schema migrations and migrate into an empty target database:

```bash
py database/migrate_sqlite_to_postgres.py --apply-schema
```

Clear existing migrated commerce data and migrate again:

```bash
py database/migrate_sqlite_to_postgres.py --apply-schema --clear-target
```
