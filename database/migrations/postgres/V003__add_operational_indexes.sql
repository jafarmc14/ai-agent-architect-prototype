ALTER TABLE users
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE product_variants
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE inventory
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE order_items
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE shopping_carts
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE shopping_cart_items
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE support_tickets
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE llm_requests
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE evaluation_runs
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

ALTER TABLE evaluation_results
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users (tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant_email ON users (tenant_id, email);
CREATE INDEX IF NOT EXISTS idx_users_tenant_external_id ON users (tenant_id, external_id);

CREATE INDEX IF NOT EXISTS idx_products_tenant_id ON products (tenant_id);
CREATE INDEX IF NOT EXISTS idx_products_tenant_category ON products (tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_products_sku_lookup ON products (lower(sku)) WHERE sku IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_products_category_lookup ON products (lower(category));
CREATE INDEX IF NOT EXISTS idx_products_metadata_gin ON products USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_product_variants_tenant_id ON product_variants (tenant_id);
CREATE INDEX IF NOT EXISTS idx_product_variants_tenant_product_id ON product_variants (tenant_id, product_id);
CREATE INDEX IF NOT EXISTS idx_product_variants_sku_lookup ON product_variants (lower(sku)) WHERE sku IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_product_variants_attributes_gin ON product_variants USING gin (attributes);

CREATE INDEX IF NOT EXISTS idx_inventory_tenant_id ON inventory (tenant_id);
CREATE INDEX IF NOT EXISTS idx_inventory_tenant_product_id ON inventory (tenant_id, product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_tenant_variant_id ON inventory (tenant_id, product_variant_id);

CREATE INDEX IF NOT EXISTS idx_orders_tenant_id ON orders (tenant_id);
CREATE INDEX IF NOT EXISTS idx_orders_tenant_user_id ON orders (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_orders_tenant_order_number ON orders (tenant_id, order_number);
CREATE INDEX IF NOT EXISTS idx_orders_tenant_status ON orders (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_metadata_gin ON orders USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_order_items_tenant_id ON order_items (tenant_id);
CREATE INDEX IF NOT EXISTS idx_order_items_tenant_order_id ON order_items (tenant_id, order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_sku_lookup ON order_items (lower(sku)) WHERE sku IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shopping_carts_tenant_id ON shopping_carts (tenant_id);
CREATE INDEX IF NOT EXISTS idx_shopping_carts_tenant_user_id ON shopping_carts (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_shopping_carts_tenant_session_id ON shopping_carts (tenant_id, session_id);
CREATE INDEX IF NOT EXISTS idx_shopping_carts_metadata_gin ON shopping_carts USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_shopping_cart_items_tenant_id ON shopping_cart_items (tenant_id);
CREATE INDEX IF NOT EXISTS idx_shopping_cart_items_tenant_cart_id ON shopping_cart_items (tenant_id, shopping_cart_id);

CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant_id ON support_tickets (tenant_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant_user_id ON support_tickets (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant_status ON support_tickets (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant_conversation_id ON support_tickets (tenant_id, conversation_id);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_source ON documents (tenant_id, source);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_language ON documents (tenant_id, language);
CREATE INDEX IF NOT EXISTS idx_documents_metadata_gin ON documents USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_id ON document_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_document_id ON document_chunks (tenant_id, document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_metadata_gin ON document_chunks USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_conversations_tenant_id ON conversations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_conversations_tenant_user_id ON conversations (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_tenant_session_id ON conversations (tenant_id, session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_metadata_gin ON conversations USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_messages_tenant_id ON messages (tenant_id);
CREATE INDEX IF NOT EXISTS idx_messages_tenant_conversation_id ON messages (tenant_id, conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_metadata_gin ON messages USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_llm_requests_tenant_id ON llm_requests (tenant_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_tenant_conversation_id ON llm_requests (tenant_id, conversation_id);
CREATE INDEX IF NOT EXISTS idx_llm_requests_metadata_gin ON llm_requests USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_tenant_id ON evaluation_runs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_results_tenant_id ON evaluation_results (tenant_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_results_tenant_run_id ON evaluation_results (tenant_id, evaluation_run_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_vector
ON document_chunks
USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100)
WHERE embedding_vector IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('V003', 'add tenant-aware operational indexes')
ON CONFLICT (version) DO NOTHING;
