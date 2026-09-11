-- V017 changed the schema before its ledger insert was present in some databases.
-- Keep this repair idempotent and give the repair itself a unique version.
INSERT INTO schema_migrations (version, description)
VALUES ('V017', 'add token and context observability')
ON CONFLICT (version) DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES ('V034', 'repair token context migration ledger')
ON CONFLICT (version) DO NOTHING;
