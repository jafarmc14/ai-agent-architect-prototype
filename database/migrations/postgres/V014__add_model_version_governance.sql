ALTER TABLE llm_requests
    ADD COLUMN IF NOT EXISTS model_version TEXT,
    ADD COLUMN IF NOT EXISTS model_key TEXT,
    ADD COLUMN IF NOT EXISTS model_pinned BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_llm_requests_model_version
    ON llm_requests (provider, model, model_version, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_requests_model_key
    ON llm_requests (model_key, created_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('V014', 'add model version governance')
ON CONFLICT (version) DO NOTHING;
