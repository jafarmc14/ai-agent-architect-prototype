# PostgreSQL Schema Design

Phase 5 introduces the target PostgreSQL schema for the AI commerce agent. This is a design artifact first; the application runtime still uses SQLite until the repository layer is migrated.

## Scope

The initial PostgreSQL schema covers:

- customers and agent users
- catalog, variants, and inventory
- orders and order items
- shopping carts and cart items
- support tickets
- knowledge documents and pgvector-backed chunks
- conversations and messages
- LLM request telemetry
- evaluation runs and results

## Tables

| Table | Purpose |
|---|---|
| `users` | Customer/admin identity and contact profile. |
| `products` | Product catalog parent records. |
| `product_variants` | Sellable product variants such as size, color, or edition. |
| `inventory` | Stock by product/variant/location. |
| `orders` | Order header, customer snapshot, status, totals, and shipping info. |
| `order_items` | Immutable product line snapshots for each order. |
| `shopping_carts` | User or anonymous session cart headers. |
| `shopping_cart_items` | Cart line items. |
| `support_tickets` | Human escalation cases created by the agent. |
| `documents` | Knowledge base source documents. |
| `document_chunks` | Searchable document chunks with pgvector embeddings. |
| `conversations` | Chat sessions across Streamlit or future channels. |
| `messages` | System, user, assistant, and tool messages. |
| `llm_requests` | Provider/model request and response telemetry. |
| `evaluation_runs` | Baseline/evaluation run metadata and aggregate summary. |
| `evaluation_results` | Per-case evaluation result details. |

## Main Relationships

| Relationship | Cardinality |
|---|---|
| `products` -> `product_variants` | One product has many variants. |
| `products` / `product_variants` -> `inventory` | A product or variant can have inventory rows by location. |
| `users` -> `orders` | One user can have many orders. |
| `orders` -> `order_items` | One order has many line items. |
| `users` -> `shopping_carts` | One user can have carts; anonymous carts use `session_id`. |
| `shopping_carts` -> `shopping_cart_items` | One cart has many line items. |
| `users` -> `support_tickets` | A user can have many support tickets. |
| `documents` -> `document_chunks` | One document has many chunks. |
| `users` -> `conversations` | One user can have many conversations. |
| `conversations` -> `messages` | One conversation has many messages. |
| `conversations` -> `llm_requests` | One conversation can have many LLM requests. |
| `evaluation_runs` -> `evaluation_results` | One evaluation run has many case results. |

## Design Notes

- UUID primary keys are used for future distributed/runtime compatibility.
- `order_number` stores the human-facing ID such as `ORD001`.
- Order items store product snapshots (`product_name`, `sku`, `unit_price`) so historical orders remain stable if catalog data changes.
- Inventory is separated from products so variants and future warehouse/location stock can be represented cleanly.
- `shopping_carts` supports both authenticated users and anonymous Streamlit sessions.
- `documents` and `document_chunks` prepare the knowledge base for database-backed retrieval.
- `V002__enable_pgvector_document_chunks.sql` enables PostgreSQL vector storage through `embedding_vector vector(1536)`.
- `V003__add_operational_indexes.sql` adds tenant-aware lookup columns and indexes for SKU, category, tenant, user, order, document metadata, and vector search access patterns.
- The vector dimension defaults to `1536` through `VECTOR_DIMENSION`, aligned with `text-embedding-3-small`; change both before generating production embeddings if a different embedding model is selected.
- `llm_requests` stores provider/model, latency, token usage, response text, tool calls, and errors for observability.
- `evaluation_runs` and `evaluation_results` mirror the current JSON baseline report shape.

## SQL Artifact

The versioned migration schema is stored at:

```text
database/migrations/postgres/V001__initial_schema.sql
database/migrations/postgres/V002__enable_pgvector_document_chunks.sql
database/migrations/postgres/V003__add_operational_indexes.sql
```

SQLite source data is migrated with:

```text
database/migrate_sqlite_to_postgres.py
```

The pgvector repository helper is stored at:

```text
core/repositories/postgres_vector_repository.py
```
