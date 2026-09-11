-- Independent of request_traces so operational log retention preserves audit evidence.
CREATE TABLE decision_records (
    tenant_id TEXT NOT NULL,
    request_id UUID NOT NULL,
    actor_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    snapshot JSONB NOT NULL,
    snapshot_sha256 TEXT NOT NULL CHECK (length(snapshot_sha256) = 64),
    PRIMARY KEY (tenant_id, request_id)
);
CREATE INDEX idx_decisions_tenant_created ON decision_records (tenant_id, created_at);

CREATE TABLE incident_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    request_id UUID NOT NULL,
    category TEXT NOT NULL CHECK (category IN
        ('negative_feedback', 'high_tokens', 'escalation', 'tool_failure', 'security_alert', 'sample')),
    status TEXT NOT NULL DEFAULT 'pending_review' CHECK
        (status IN ('pending_review', 'regression_linked', 'dismissed')),
    regression_case_id TEXT,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, request_id, category),
    CHECK (status != 'regression_linked' OR
        (regression_case_id IS NOT NULL AND reviewed_by IS NOT NULL)),
    CHECK (status != 'dismissed' OR reviewed_by IS NOT NULL)
);
CREATE INDEX idx_incidents_tenant_status ON incident_cases (tenant_id, status, created_at);

CREATE TABLE retention_holds (
    tenant_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version, description)
VALUES ('V027', 'redacted decision audit, incident review queue and retention holds')
ON CONFLICT (version) DO NOTHING;
