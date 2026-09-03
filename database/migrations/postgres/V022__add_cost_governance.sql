ALTER TABLE resource_usage_events
    ADD COLUMN IF NOT EXISTS session_id TEXT,
    ADD COLUMN IF NOT EXISTS user_id TEXT;

CREATE INDEX IF NOT EXISTS idx_resource_usage_session_cost
    ON resource_usage_events (session_id, created_at DESC)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_resource_usage_customer_cost
    ON resource_usage_events (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS tenant_ai_budgets (
    tenant_id TEXT PRIMARY KEY,
    monthly_budget_usd NUMERIC(18, 6) NOT NULL CHECK (monthly_budget_usd >= 0),
    warning_threshold NUMERIC(5, 4) NOT NULL DEFAULT 0.8
        CHECK (warning_threshold > 0 AND warning_threshold <= 1),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_resource_usage_tenant_monthly_cost
    ON resource_usage_events (tenant_id, created_at DESC, cost_usd)
    WHERE completed_at IS NOT NULL AND status <> 'blocked';

INSERT INTO schema_migrations (version, description)
VALUES ('V022', 'add session/customer cost dimensions and monthly tenant AI budgets')
ON CONFLICT (version) DO NOTHING;
