ALTER TABLE production_quality_events ADD COLUMN evaluation_sampled_at TIMESTAMPTZ;
ALTER TABLE pilot_feedback ADD COLUMN evaluation_sampled_at TIMESTAMPTZ;
CREATE INDEX idx_quality_unsampled ON production_quality_events (tenant_id, created_at)
    WHERE evaluation_sampled_at IS NULL;
CREATE INDEX idx_feedback_unsampled ON pilot_feedback (tenant_id, updated_at);
INSERT INTO schema_migrations (version, description)
VALUES ('V032', 'durable continuous-evaluation backlog and delayed-feedback resampling')
ON CONFLICT (version) DO NOTHING;
