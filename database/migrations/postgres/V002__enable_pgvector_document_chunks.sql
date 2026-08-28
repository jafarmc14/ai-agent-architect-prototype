CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS embedding_vector vector(1536),
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER CHECK (
        embedding_dimensions IS NULL OR embedding_dimensions > 0
    );

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_vector
ON document_chunks
USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 100)
WHERE embedding_vector IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_model
ON document_chunks (embedding_model);

INSERT INTO schema_migrations (version, description)
VALUES ('V002', 'enable pgvector for document chunk vector storage')
ON CONFLICT (version) DO NOTHING;
