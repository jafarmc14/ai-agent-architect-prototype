ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS structured_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_conversations_structured_state_gin
    ON conversations USING gin (structured_state);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages (conversation_id, created_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('V012', 'add structured conversation state')
ON CONFLICT (version) DO NOTHING;
