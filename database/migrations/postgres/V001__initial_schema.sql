CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    checksum TEXT,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE order_status AS ENUM (
    'awaiting_payment',
    'processing',
    'shipped',
    'completed',
    'cancelled'
);

CREATE TYPE support_ticket_priority AS ENUM (
    'low',
    'normal',
    'high',
    'urgent'
);

CREATE TYPE support_ticket_status AS ENUM (
    'open',
    'in_progress',
    'resolved',
    'closed'
);

CREATE TYPE message_role AS ENUM (
    'system',
    'user',
    'assistant',
    'tool'
);

CREATE TYPE llm_request_status AS ENUM (
    'success',
    'error',
    'rate_limited'
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id TEXT UNIQUE,
    name TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    default_shipping_address TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku TEXT UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    brand TEXT,
    country_of_origin TEXT,
    base_price NUMERIC(12, 2) NOT NULL CHECK (base_price >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'IDR',
    is_active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE product_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sku TEXT UNIQUE,
    name TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    price NUMERIC(12, 2) CHECK (price IS NULL OR price >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'IDR',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    product_variant_id UUID REFERENCES product_variants(id) ON DELETE CASCADE,
    location_code TEXT NOT NULL DEFAULT 'default',
    quantity_on_hand INTEGER NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
    quantity_reserved INTEGER NOT NULL DEFAULT 0 CHECK (quantity_reserved >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT inventory_variant_product_required CHECK (
        product_variant_id IS NULL OR product_id IS NOT NULL
    ),
    CONSTRAINT inventory_available_non_negative CHECK (
        quantity_on_hand >= quantity_reserved
    ),
    UNIQUE (product_id, product_variant_id, location_code)
);

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number TEXT NOT NULL UNIQUE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    customer_name TEXT,
    customer_email TEXT,
    status order_status NOT NULL DEFAULT 'processing',
    shipping_address TEXT,
    subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    shipping_total NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (shipping_total >= 0),
    discount_total NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (discount_total >= 0),
    tax_total NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (tax_total >= 0),
    grand_total NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (grand_total >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'IDR',
    order_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    estimated_arrival TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id) ON DELETE SET NULL,
    product_variant_id UUID REFERENCES product_variants(id) ON DELETE SET NULL,
    product_name TEXT NOT NULL,
    sku TEXT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'IDR',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE shopping_carts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT,
    currency CHAR(3) NOT NULL DEFAULT 'IDR',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT shopping_carts_owner_required CHECK (
        user_id IS NOT NULL OR session_id IS NOT NULL
    ),
    UNIQUE (session_id)
);

CREATE TABLE shopping_cart_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shopping_cart_id UUID NOT NULL REFERENCES shopping_carts(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    product_variant_id UUID REFERENCES product_variants(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'IDR',
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (shopping_cart_id, product_id, product_variant_id)
);

CREATE TABLE support_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_number TEXT UNIQUE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    conversation_id UUID,
    customer_message TEXT NOT NULL,
    agent_summary TEXT,
    priority support_ticket_priority NOT NULL DEFAULT 'normal',
    status support_ticket_status NOT NULL DEFAULT 'open',
    assigned_to_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    source TEXT,
    source_type TEXT NOT NULL DEFAULT 'text',
    version TEXT,
    language TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL,
    token_count INTEGER CHECK (token_count IS NULL OR token_count >= 0),
    embedding JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    session_id TEXT,
    channel TEXT NOT NULL DEFAULT 'streamlit',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role message_role NOT NULL,
    content TEXT NOT NULL,
    tool_name TEXT,
    tool_call_id TEXT,
    tool_arguments JSONB,
    tool_output JSONB,
    llm_request_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE llm_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    request_messages JSONB,
    request_tools JSONB,
    response_text TEXT,
    response_tool_calls JSONB,
    status llm_request_status NOT NULL,
    error_code TEXT,
    error_message TEXT,
    latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    prompt_tokens INTEGER CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    completion_tokens INTEGER CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    total_tokens INTEGER CHECK (total_tokens IS NULL OR total_tokens >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE support_tickets
    ADD CONSTRAINT support_tickets_conversation_fk
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL;

ALTER TABLE messages
    ADD CONSTRAINT messages_llm_request_fk
    FOREIGN KEY (llm_request_id) REFERENCES llm_requests(id) ON DELETE SET NULL;

CREATE TABLE evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    environment TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    dataset_name TEXT NOT NULL,
    dataset_path TEXT,
    total_cases INTEGER NOT NULL DEFAULT 0 CHECK (total_cases >= 0),
    evaluated_cases INTEGER NOT NULL DEFAULT 0 CHECK (evaluated_cases >= 0),
    skipped_cases INTEGER NOT NULL DEFAULT 0 CHECK (skipped_cases >= 0),
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE evaluation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    dataset_file TEXT,
    query TEXT NOT NULL,
    expected_tool JSONB,
    expected_arguments JSONB,
    actual_tools JSONB,
    actual_tool_calls JSONB,
    response_text TEXT,
    exception TEXT,
    tool_selection_pass BOOLEAN NOT NULL DEFAULT false,
    argument_accuracy_pass BOOLEAN NOT NULL DEFAULT false,
    response_returned BOOLEAN NOT NULL DEFAULT false,
    skipped BOOLEAN NOT NULL DEFAULT false,
    skip_reason TEXT,
    latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    access TEXT,
    risk TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (evaluation_run_id, case_id)
);

CREATE INDEX idx_products_category ON products (category);
CREATE INDEX idx_products_active ON products (is_active);
CREATE INDEX idx_product_variants_product_id ON product_variants (product_id);
CREATE INDEX idx_inventory_product_id ON inventory (product_id);
CREATE INDEX idx_inventory_variant_id ON inventory (product_variant_id);
CREATE INDEX idx_orders_order_number ON orders (order_number);
CREATE INDEX idx_orders_user_id ON orders (user_id);
CREATE INDEX idx_orders_status ON orders (status);
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_shopping_carts_user_id ON shopping_carts (user_id);
CREATE INDEX idx_shopping_cart_items_cart_id ON shopping_cart_items (shopping_cart_id);
CREATE INDEX idx_support_tickets_status ON support_tickets (status);
CREATE INDEX idx_support_tickets_priority ON support_tickets (priority);
CREATE INDEX idx_documents_source ON documents (source);
CREATE INDEX idx_document_chunks_document_id ON document_chunks (document_id);
CREATE INDEX idx_conversations_user_id ON conversations (user_id);
CREATE INDEX idx_conversations_session_id ON conversations (session_id);
CREATE INDEX idx_messages_conversation_id ON messages (conversation_id);
CREATE INDEX idx_llm_requests_conversation_id ON llm_requests (conversation_id);
CREATE INDEX idx_llm_requests_provider_model ON llm_requests (provider, model);
CREATE INDEX idx_evaluation_runs_dataset_name ON evaluation_runs (dataset_name);
CREATE INDEX idx_evaluation_results_run_id ON evaluation_results (evaluation_run_id);

INSERT INTO schema_migrations (version, description)
VALUES ('V001', 'initial PostgreSQL schema')
ON CONFLICT (version) DO NOTHING;
