# PostgreSQL Schema Design

Phase 5 introduced the target PostgreSQL schema for the AI commerce agent. The application runtime can now use PostgreSQL through `DATABASE_PROVIDER=postgres`, with SQLite preserved as a rollback and migration source.

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
- `V002__enable_pgvector_document_chunks.sql` enables PostgreSQL vector storage through `embedding_vector`.
- `V003__add_operational_indexes.sql` adds tenant-aware lookup columns and indexes for SKU, category, tenant, user, order, document metadata, and vector search access patterns.
- `V004__add_product_embeddings.sql` adds pgvector-backed product embedding storage and vector search indexing.
- `V005__use_ollama_embedding_dimensions.sql` changes product and document vector columns to `vector(768)`, aligned with Ollama `nomic-embed-text`.
- `V006__add_product_keyword_search_index.sql` adds the GIN full-text index used by hybrid product search.
- `V007__add_document_freshness_fields.sql` adds queryable document freshness fields for RAG retrieval.
- The vector dimension defaults to `768` through `VECTOR_DIMENSION`, aligned with local Ollama `nomic-embed-text`.
- `llm_requests` stores provider/model, latency, token usage, response text, tool calls, and errors for observability.
- `evaluation_runs` and `evaluation_results` mirror the current JSON baseline report shape.

## Product Search Indexing

The product search foundation keeps deterministic filters as structured SQL conditions:

```text
category
min_price
max_price
```

In PostgreSQL, category filtering maps to `products.category` and price filtering maps to `products.base_price`. `V003__add_operational_indexes.sql` includes category and tenant/category indexes so these filters remain database-native and predictable.

Structured query extraction currently captures:

```json
{
  "category": "Shoes",
  "catalog_category": "Shoes",
  "size": 42,
  "color": "black",
  "waterproof": true,
  "min_price": 0,
  "max_price": 500000
}
```

`catalog_category` is the canonical category used for deterministic SQL filtering. More specific phrases such as `hiking shoes` can still be preserved in `query`/`category` for future semantic ranking, while SQL filtering remains aligned with the current catalog taxonomy.

Constraints are separated before repository access:

```text
Hard constraints:
price, size, availability, SKU, stock

Soft constraints:
comfortable, minimalist, good for winter
```

PostgreSQL repositories currently enforce price, size, SKU, availability, and minimum stock as SQL filters. These factual filters must stay in the database/repository layer, not in LLM final-response reasoning. Size is evaluated against `product_variants.attributes`; with the current migrated seed data, size-specific searches may return no exact match until variant attributes are populated. Soft constraints are used for semantic ranking and should not narrow SQL results directly.

Hybrid product search is layered on top of hard filters for discovery and ranking:

```text
SQL hard filters
+
keyword search
+
vector search
```

`ProductService` embeds the semantic query text with local Ollama, sends keyword text alongside the vector, then `PostgresProductEmbeddingRepository` retrieves the top 20 eligible products with a hybrid score. The service applies a deterministic reranker and returns the top 5 final products:

```text
Top 20
↓
reranker
↓
Top 5
```

Exact category, price, SKU, stock, availability, and size filters stay deterministic.

## Product Embeddings

Product embeddings are stored directly on `products`:

```text
embedding_vector
embedding_model
embedding_dimensions
embedding_source_text
embedding_updated_at
```

Only relevant semantic fields are embedded:

```text
name
description
category
brand
country_of_origin
variant_names
variant_attributes
```

Factual filter fields are intentionally excluded from embedding text:

```text
id
sku
base_price
currency
stock
quantity_on_hand
quantity_reserved
created_at
updated_at
```

Hard constraints such as price, stock, SKU, availability, and size must stay in SQL filters. Product embeddings are for semantic discovery and ranking only. Local development uses Ollama `nomic-embed-text` embeddings with 768 dimensions.

## Knowledge Document Ingestion

Proper RAG ingestion uses split Markdown policy documents from `knowledge_base/*.md`:

```text
return_policy
refund_policy
shipping_policy
warranty
payments
faq
```

The ingestion pipeline is:

```text
parse
clean
chunk
embed
store
```

`database/ingest_knowledge_base.py` runs the pipeline. It upserts each source document into `documents`, replaces that document's old chunks, embeds each cleaned chunk with the configured embedding provider, and stores the result in `document_chunks.embedding_vector`.

Current local ingestion uses Ollama `nomic-embed-text` and stores `vector(768)` chunks in PostgreSQL.

Each source document carries front matter metadata:

```text
document_id
title
version
effective_date
expires_at
status
superseded_by
source
category
tenant_id
access_level
trust_level
```

`tenant_id` is also written to the native `documents.tenant_id` and `document_chunks.tenant_id` columns. The full metadata object is copied into both `documents.metadata` and each chunk's `document_chunks.metadata` so retrieval can enforce status, access, trust, tenant, and source filters in later RAG phases.

Freshness fields are also written to native `documents` columns:

```text
effective_date
expires_at
status
superseded_by
```

Vector chunk retrieval filters out inactive, expired, future-effective, and superseded documents.

## Knowledge Retrieval

Policy retrieval is authorization-first:

```text
query
|
v
authorization scope
|
v
embedding
|
v
metadata filter
|
v
vector retrieval
|
v
trust-aware reranker
|
v
context
```

The PostgreSQL retrieval query applies tenant, role, department, access level, document status, freshness, supersession, and trust-level filters before vector retrieval. Unauthorized chunks are not retrieved first and filtered later.

Default retrieval scope:

```text
tenant_id = default
role = customer
department = public
access_level = public
```

Supported trust levels:

```text
OFFICIAL
INTERNAL_APPROVED
INTERNAL_DRAFT
USER_GENERATED
EXTERNAL
```

Retrieval ranking combines vector similarity and trust weight so official policy evidence is preferred over lower-trust content when relevance is close. The RAG workflow then builds context with citation metadata and abstains when there is not enough authorized, fresh evidence.

## SQL Artifact

The versioned migration schema is stored at:

```text
database/migrations/postgres/V001__initial_schema.sql
database/migrations/postgres/V002__enable_pgvector_document_chunks.sql
database/migrations/postgres/V003__add_operational_indexes.sql
database/migrations/postgres/V004__add_product_embeddings.sql
database/migrations/postgres/V005__use_ollama_embedding_dimensions.sql
database/migrations/postgres/V006__add_product_keyword_search_index.sql
database/migrations/postgres/V007__add_document_freshness_fields.sql
```

SQLite source data is migrated with:

```text
database/migrate_sqlite_to_postgres.py
```

The pgvector repository helper is stored at:

```text
core/repositories/postgres_vector_repository.py
```
