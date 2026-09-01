CREATE TABLE IF NOT EXISTS resource_usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID,
    trace_id UUID,
    tenant_id TEXT NOT NULL,
    identity_key TEXT NOT NULL,
    workflow TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'completed', 'blocked', 'error')),
    limit_code TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    tool_calls INTEGER NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
    agent_steps INTEGER NOT NULL DEFAULT 0 CHECK (agent_steps >= 0),
    runtime_ms INTEGER NOT NULL DEFAULT 0 CHECK (runtime_ms >= 0),
    cost_usd NUMERIC(18, 10) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_resource_usage_identity_time
    ON resource_usage_events (identity_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_resource_usage_tenant_time
    ON resource_usage_events (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_resource_usage_repetition
    ON resource_usage_events (identity_key, input_hash, workflow, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_resource_usage_request
    ON resource_usage_events (request_id) WHERE request_id IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('V018', 'add denial-of-wallet and resource abuse protection')
ON CONFLICT (version) DO NOTHING;
