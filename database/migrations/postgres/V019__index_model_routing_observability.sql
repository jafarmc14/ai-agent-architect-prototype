CREATE INDEX IF NOT EXISTS idx_llm_requests_routing_tier
    ON llm_requests ((metadata->'routing'->>'selected_tier'), created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_requests_premium_model_usage
    ON llm_requests (created_at DESC)
    WHERE metadata->'routing'->>'premium_model_used' = 'true';

INSERT INTO schema_migrations (version, description)
VALUES ('V019', 'index model routing and premium-model usage metadata')
ON CONFLICT (version) DO NOTHING;
