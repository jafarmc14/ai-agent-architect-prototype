CREATE TABLE IF NOT EXISTS prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id TEXT NOT NULL,
    version TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'archived', 'rollback')),
    evaluation_score NUMERIC(8, 6),
    previous_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (prompt_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_versions_one_active
    ON prompt_versions (prompt_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_prompt_versions_prompt_status
    ON prompt_versions (prompt_id, status);

ALTER TABLE llm_requests
    ADD COLUMN IF NOT EXISTS prompt_id TEXT,
    ADD COLUMN IF NOT EXISTS prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS prompt_key TEXT;

CREATE INDEX IF NOT EXISTS idx_llm_requests_prompt_version
    ON llm_requests (prompt_id, prompt_version, created_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('V013', 'add prompt versioning')
ON CONFLICT (version) DO NOTHING;
