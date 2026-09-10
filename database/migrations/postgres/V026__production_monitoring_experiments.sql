CREATE TABLE production_quality_events (
    request_id UUID PRIMARY KEY REFERENCES request_traces(request_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    review JSONB,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ
);
CREATE INDEX idx_quality_tenant_time ON production_quality_events (tenant_id, created_at DESC);

CREATE TABLE production_drift_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fingerprints JSONB NOT NULL
);
CREATE INDEX idx_drift_tenant_time ON production_drift_snapshots (tenant_id, created_at DESC);

CREATE TABLE shadow_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES request_traces(request_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','error','expired')),
    payload JSONB NOT NULL,
    result JSONB,
    finished_at TIMESTAMPTZ,
    UNIQUE (request_id, experiment_id)
);
CREATE INDEX idx_shadow_pending ON shadow_jobs (created_at) WHERE status = 'pending';
CREATE INDEX idx_shadow_tenant_time ON shadow_jobs (tenant_id, created_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('V026', 'production quality, drift snapshots and isolated shadow jobs')
ON CONFLICT (version) DO NOTHING;
