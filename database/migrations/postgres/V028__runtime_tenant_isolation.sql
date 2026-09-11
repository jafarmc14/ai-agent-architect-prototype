DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_agent_runtime') THEN
        CREATE ROLE ai_agent_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
    EXECUTE format('GRANT ai_agent_runtime TO %I', current_user);
END $$;
GRANT USAGE ON SCHEMA public TO ai_agent_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_agent_runtime;

DO $$
DECLARE t record;
BEGIN
    FOR t IN SELECT table_name FROM information_schema.columns
             WHERE table_schema = 'public' AND column_name = 'tenant_id'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t.table_name);
        EXECUTE format('CREATE POLICY runtime_tenant ON %I TO ai_agent_runtime USING
            (tenant_id = current_setting(''app.tenant_id'', true)) WITH CHECK
            (tenant_id = current_setting(''app.tenant_id'', true))', t.table_name);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id SET DEFAULT COALESCE(NULLIF(current_setting(''app.tenant_id'', true), ''''), ''default'')', t.table_name);
        EXECUTE format('GRANT INSERT, UPDATE, DELETE ON %I TO ai_agent_runtime', t.table_name);
    END LOOP;
END $$;

ALTER TABLE trace_spans ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_spans FORCE ROW LEVEL SECURITY;
CREATE POLICY runtime_trace_tenant ON trace_spans TO ai_agent_runtime
    USING (EXISTS (SELECT 1 FROM request_traces r WHERE r.trace_id = trace_spans.trace_id))
    WITH CHECK (EXISTS (SELECT 1 FROM request_traces r WHERE r.trace_id = trace_spans.trace_id));
GRANT INSERT, UPDATE ON trace_spans TO ai_agent_runtime;
REVOKE UPDATE, DELETE ON decision_records, audit_logs FROM ai_agent_runtime;
REVOKE INSERT, UPDATE, DELETE ON retention_holds FROM ai_agent_runtime;

INSERT INTO schema_migrations (version, description)
VALUES ('V028', 'request-scoped non-bypass RLS role and append-only audit grants')
ON CONFLICT (version) DO NOTHING;
