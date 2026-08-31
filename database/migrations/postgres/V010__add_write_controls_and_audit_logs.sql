CREATE TABLE IF NOT EXISTS write_idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL DEFAULT 'default',
    idempotency_key TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    request_id TEXT,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    response TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL DEFAULT 'default',
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    actor_role TEXT NOT NULL DEFAULT 'anonymous',
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    old_value JSONB,
    new_value JSONB,
    request_id TEXT,
    idempotency_key TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_write_idempotency_tenant_action
    ON write_idempotency_keys (tenant_id, action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_actor
    ON audit_logs (tenant_id, actor_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_resource
    ON audit_logs (resource_type, resource_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id
    ON audit_logs (request_id);

INSERT INTO schema_migrations (version, description)
VALUES ('V010', 'add write action idempotency keys and audit logs')
ON CONFLICT (version) DO NOTHING;
