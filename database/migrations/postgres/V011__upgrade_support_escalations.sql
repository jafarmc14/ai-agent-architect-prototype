ALTER TABLE support_tickets
    ADD COLUMN IF NOT EXISTS escalation_type TEXT,
    ADD COLUMN IF NOT EXISTS escalation_reason TEXT,
    ADD COLUMN IF NOT EXISTS summarized_context TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_support_tickets_escalation_type
    ON support_tickets (tenant_id, escalation_type, created_at DESC);

INSERT INTO schema_migrations (version, description)
VALUES ('V011', 'upgrade support tickets with escalation context fields')
ON CONFLICT (version) DO NOTHING;
