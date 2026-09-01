INSERT INTO schema_migrations (version, description)
VALUES
    ('V017', 'add token and context observability'),
    ('V019', 'repair token context migration ledger')
ON CONFLICT (version) DO NOTHING;
