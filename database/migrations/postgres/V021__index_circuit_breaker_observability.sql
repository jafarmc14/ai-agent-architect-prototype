CREATE INDEX IF NOT EXISTS idx_llm_requests_circuit_open_failure
    ON llm_requests (provider, model, created_at DESC)
    WHERE metadata->'fallback'->'attempt'->'circuit'->'after'->>'state' = 'open';

CREATE INDEX IF NOT EXISTS idx_trace_spans_circuit_open
    ON trace_spans (started_at DESC)
    WHERE name = 'llm.circuit_open';

INSERT INTO schema_migrations (version, description)
VALUES ('V021', 'index circuit breaker open transitions and skipped calls')
ON CONFLICT (version) DO NOTHING;
