ALTER TABLE products
    ADD COLUMN IF NOT EXISTS embedding_vector vector(1536),
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER CHECK (
        embedding_dimensions IS NULL OR embedding_dimensions > 0
    ),
    ADD COLUMN IF NOT EXISTS embedding_source_text TEXT,
    ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_products_embedding_vector
ON products
USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100)
WHERE embedding_vector IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_products_embedding_model
ON products (embedding_model);

INSERT INTO schema_migrations (version, description)
VALUES ('V004', 'add product embedding storage')
ON CONFLICT (version) DO NOTHING;
