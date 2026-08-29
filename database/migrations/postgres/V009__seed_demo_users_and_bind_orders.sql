INSERT INTO users (external_id, name, email, metadata)
SELECT DISTINCT
    'demo-' || lower(regexp_replace(customer_name, '[^a-zA-Z0-9]+', '-', 'g')) AS external_id,
    customer_name AS name,
    lower(regexp_replace(customer_name, '[^a-zA-Z0-9]+', '.', 'g')) || '@example.local' AS email,
    jsonb_build_object('role', 'customer', 'tenant_id', 'default', 'source', 'demo_seed')
FROM orders
WHERE customer_name IS NOT NULL
ON CONFLICT (email) DO UPDATE SET
    name = EXCLUDED.name,
    metadata = users.metadata || EXCLUDED.metadata,
    updated_at = now();

UPDATE orders o
SET user_id = u.id,
    customer_email = u.email,
    updated_at = now()
FROM users u
WHERE o.customer_name = u.name
  AND u.metadata->>'source' = 'demo_seed'
  AND o.user_id IS NULL;

UPDATE shopping_carts sc
SET metadata = sc.metadata || jsonb_build_object('auth_note', 'legacy anonymous cart from sqlite migration'),
    updated_at = now()
WHERE sc.user_id IS NULL;

INSERT INTO schema_migrations (version, description)
VALUES ('V009', 'seed demo users and bind migrated orders')
ON CONFLICT (version) DO NOTHING;
