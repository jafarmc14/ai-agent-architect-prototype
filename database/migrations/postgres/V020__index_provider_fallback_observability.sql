CREATE INDEX IF NOT EXISTS idx_llm_requests_provider_fallback
    ON llm_requests (created_at DESC)
    WHERE metadata->'fallback'->>'fallback_used' = 'true';

CREATE INDEX IF NOT EXISTS idx_llm_requests_fallback_failure_category
    ON llm_requests ((metadata->'fallback'->'attempt'->'failure'->>'category'), created_at DESC)
    WHERE metadata->'fallback'->'attempt'->>'status' = 'error';

INSERT INTO schema_migrations (version, description)
VALUES ('V020', 'index provider fallback success and failure metadata')
ON CONFLICT (version) DO NOTHING;
