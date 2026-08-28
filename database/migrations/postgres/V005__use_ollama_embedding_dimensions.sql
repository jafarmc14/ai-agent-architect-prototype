DROP INDEX IF EXISTS idx_products_embedding_vector;
DROP INDEX IF EXISTS idx_document_chunks_embedding_vector;

UPDATE products
SET embedding_vector = NULL,
    embedding_dimensions = NULL,
    embedding_source_text = NULL,
    embedding_updated_at = NULL
WHERE embedding_vector IS NOT NULL
  AND embedding_dimensions IS DISTINCT FROM 768;

UPDATE document_chunks
SET embedding_vector = NULL,
    embedding_dimensions = NULL
WHERE embedding_vector IS NOT NULL
  AND embedding_dimensions IS DISTINCT FROM 768;

ALTER TABLE products
    ALTER COLUMN embedding_vector TYPE vector(768)
    USING embedding_vector::vector(768);

ALTER TABLE document_chunks
    ALTER COLUMN embedding_vector TYPE vector(768)
    USING embedding_vector::vector(768);

CREATE INDEX IF NOT EXISTS idx_products_embedding_vector
ON products
USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100)
WHERE embedding_vector IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_vector
ON document_chunks
USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100)
WHERE embedding_vector IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('V005', 'use Ollama nomic-embed-text vector dimensions')
ON CONFLICT (version) DO NOTHING;
