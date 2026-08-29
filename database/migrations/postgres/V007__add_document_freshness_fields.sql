ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS effective_date DATE,
    ADD COLUMN IF NOT EXISTS expires_at DATE,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS superseded_by TEXT;

UPDATE documents
SET effective_date = COALESCE(effective_date, NULLIF(metadata->>'effective_date', '')::date),
    expires_at = COALESCE(expires_at, NULLIF(metadata->>'expires_at', '')::date),
    status = COALESCE(NULLIF(metadata->>'status', ''), status, 'active'),
    superseded_by = COALESCE(superseded_by, NULLIF(metadata->>'superseded_by', ''))
WHERE metadata IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_freshness
ON documents (tenant_id, status, effective_date, expires_at);

CREATE INDEX IF NOT EXISTS idx_documents_superseded_by
ON documents (superseded_by)
WHERE superseded_by IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('V007', 'add document freshness fields')
ON CONFLICT (version) DO NOTHING;
