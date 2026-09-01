CREATE TABLE IF NOT EXISTS request_traces (
    request_id UUID PRIMARY KEY,
    trace_id UUID NOT NULL UNIQUE,
    session_id TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    user_id TEXT,
    request_input TEXT,
    response_output TEXT,
    intent TEXT,
    workflow TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'error')),
    latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS trace_spans (
    id UUID PRIMARY KEY,
    trace_id UUID NOT NULL REFERENCES request_traces(trace_id) ON DELETE CASCADE,
    parent_span_id UUID REFERENCES trace_spans(id) ON DELETE SET NULL,
    stage TEXT NOT NULL
        CHECK (stage IN ('request', 'intent', 'retrieval', 'tool', 'llm', 'validation', 'response')),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'error', 'blocked')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT
);

ALTER TABLE llm_requests
    ADD COLUMN IF NOT EXISTS request_id UUID REFERENCES request_traces(request_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS trace_id UUID,
    ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(18, 10)
        CHECK (cost_usd IS NULL OR cost_usd >= 0),
    ADD COLUMN IF NOT EXISTS cost_source TEXT;

CREATE INDEX IF NOT EXISTS idx_request_traces_trace_id
    ON request_traces (trace_id);

CREATE INDEX IF NOT EXISTS idx_request_traces_tenant_started
    ON request_traces (tenant_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_request_traces_user_started
    ON request_traces (user_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_trace_spans_trace_started
    ON trace_spans (trace_id, started_at);

CREATE INDEX IF NOT EXISTS idx_trace_spans_stage_name
    ON trace_spans (stage, name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_requests_trace_id
    ON llm_requests (trace_id, created_at);

INSERT INTO schema_migrations (version, description)
VALUES ('V015', 'add request lifecycle and tool/LLM tracing')
ON CONFLICT (version) DO NOTHING;
