ALTER TABLE shopping_carts DROP CONSTRAINT IF EXISTS shopping_carts_session_id_key;
ALTER TABLE shopping_carts ADD CONSTRAINT shopping_carts_tenant_session_key UNIQUE (tenant_id, session_id);
ALTER TABLE shopping_cart_items ALTER COLUMN currency SET DEFAULT
    COALESCE(NULLIF(current_setting('app.currency', true), ''), 'IDR');
INSERT INTO schema_migrations (version, description)
VALUES ('V033', 'tenant-local cart session uniqueness and currency defaults')
ON CONFLICT (version) DO NOTHING;
