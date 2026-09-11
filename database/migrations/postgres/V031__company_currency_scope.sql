CREATE POLICY company_currency ON products AS RESTRICTIVE TO ai_agent_runtime
    USING (currency = current_setting('app.currency', true))
    WITH CHECK (currency = current_setting('app.currency', true));
CREATE POLICY company_currency ON orders AS RESTRICTIVE TO ai_agent_runtime
    USING (currency = current_setting('app.currency', true))
    WITH CHECK (currency = current_setting('app.currency', true));
CREATE POLICY company_currency ON shopping_carts AS RESTRICTIVE TO ai_agent_runtime
    USING (currency = current_setting('app.currency', true))
    WITH CHECK (currency = current_setting('app.currency', true));
ALTER TABLE shopping_carts ALTER COLUMN currency SET DEFAULT
    COALESCE(NULLIF(current_setting('app.currency', true), ''), 'IDR');
INSERT INTO schema_migrations (version, description)
VALUES ('V031', 'company catalog/order/cart currency constraints; no implicit conversion')
ON CONFLICT (version) DO NOTHING;
