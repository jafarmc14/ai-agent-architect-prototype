-- Enforce tenant equality on new references; audit old data before VALIDATE CONSTRAINT.
DO $$
DECLARE f record; source_columns text; target_columns text; constraint_name text; index_name text;
BEGIN
    FOR f IN SELECT c.* FROM pg_constraint c
             JOIN pg_class s ON s.oid = c.conrelid JOIN pg_namespace n ON n.oid = s.relnamespace
             WHERE c.contype = 'f' AND n.nspname = 'public'
               AND EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = c.conrelid AND attname = 'tenant_id')
               AND EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = c.confrelid AND attname = 'tenant_id')
    LOOP
        SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY k.ordinality) INTO source_columns
        FROM unnest(f.conkey) WITH ORDINALITY k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = f.conrelid AND a.attnum = k.attnum;
        SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY k.ordinality) INTO target_columns
        FROM unnest(f.confkey) WITH ORDINALITY k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = f.confrelid AND a.attnum = k.attnum;
        constraint_name := 'tenant_fk_' || md5(f.conrelid::text || f.conname);
        index_name := 'tenant_ref_' || md5(f.confrelid::text || target_columns);
        EXECUTE format('CREATE UNIQUE INDEX IF NOT EXISTS %I ON %s (tenant_id, %s)', index_name, f.confrelid::regclass, target_columns);
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (tenant_id, %s)
            REFERENCES %s (tenant_id, %s) NOT VALID',
            f.conrelid::regclass, constraint_name, source_columns, f.confrelid::regclass, target_columns);
    END LOOP;
END $$;
INSERT INTO schema_migrations (version, description)
VALUES ('V030', 'same-tenant relational references for new writes; historical validation required')
ON CONFLICT (version) DO NOTHING;
