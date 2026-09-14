ALTER TABLE action_approvals
    ADD COLUMN rejected_by UUID REFERENCES users(id),
    ADD COLUMN rejected_at TIMESTAMPTZ;

ALTER TABLE action_approvals
    ADD CONSTRAINT action_approvals_one_decision
    CHECK (approved_at IS NULL OR rejected_at IS NULL);

INSERT INTO schema_migrations (version, description)
VALUES ('V035', 'record rejected order action approvals')
ON CONFLICT (version) DO NOTHING;
