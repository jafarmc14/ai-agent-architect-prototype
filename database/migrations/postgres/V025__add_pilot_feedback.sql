CREATE TABLE pilot_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES request_traces(request_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('thumbs_up', 'thumbs_down', 'wrong_answer', 'report_issue', 'request_human')),
    ticket_number TEXT REFERENCES support_tickets(ticket_number),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (request_id, user_id, kind)
);
CREATE INDEX idx_pilot_feedback_tenant_created ON pilot_feedback (tenant_id, created_at DESC);
CREATE UNIQUE INDEX idx_pilot_feedback_rating ON pilot_feedback (request_id, user_id)
    WHERE kind IN ('thumbs_up', 'thumbs_down');

INSERT INTO schema_migrations (version, description)
VALUES ('V025', 'add pilot feedback and human request tracking')
ON CONFLICT (version) DO NOTHING;
