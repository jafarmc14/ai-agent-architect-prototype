DROP INDEX IF EXISTS idx_resource_usage_tenant_monthly_cost;

CREATE INDEX idx_resource_usage_tenant_monthly_cost
    ON resource_usage_events (tenant_id, created_at DESC, cost_usd)
    WHERE completed_at IS NOT NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('V023', 'include all completed requests in tenant cost index')
ON CONFLICT (version) DO NOTHING;
