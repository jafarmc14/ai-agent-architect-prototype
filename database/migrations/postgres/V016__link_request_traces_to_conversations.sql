ALTER TABLE request_traces
    ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_request_traces_conversation
    ON request_traces (conversation_id, started_at);

INSERT INTO schema_migrations (version, description)
VALUES ('V016', 'link request traces to conversations')
ON CONFLICT (version) DO NOTHING;
