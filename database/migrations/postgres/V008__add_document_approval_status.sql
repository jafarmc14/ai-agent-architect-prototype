ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'uploaded';

UPDATE documents
SET approval_status = COALESCE(NULLIF(metadata->>'approval_status', ''), approval_status, 'uploaded')
WHERE metadata IS NOT NULL;

UPDATE documents
SET metadata = jsonb_set(metadata, '{approval_status}', to_jsonb(approval_status), true);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_status_approval
ON documents (tenant_id, status, approval_status, effective_date, expires_at);

INSERT INTO schema_migrations (version, description)
VALUES ('V008', 'add document approval status')
ON CONFLICT (version) DO NOTHING;
