CREATE TABLE action_approvals (
    tenant_id TEXT NOT NULL DEFAULT COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), 'default'),
    confirmation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    request_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '15 minutes',
    confirmed_at TIMESTAMPTZ,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, confirmation_id),
    UNIQUE (tenant_id, idempotency_key),
    CHECK (approved_by IS NULL OR approved_by != actor_user_id)
);
CREATE INDEX idx_approvals_expiry ON action_approvals (tenant_id, expires_at);
ALTER TABLE action_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_approvals FORCE ROW LEVEL SECURITY;
CREATE POLICY runtime_tenant ON action_approvals TO ai_agent_runtime
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE ON action_approvals TO ai_agent_runtime;

INSERT INTO schema_migrations (version, description)
VALUES ('V029', 'durable confirmation and independent high-risk approval checkpoints')
ON CONFLICT (version) DO NOTHING;
