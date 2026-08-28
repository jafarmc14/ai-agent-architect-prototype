CREATE INDEX IF NOT EXISTS idx_products_keyword_search
ON products
USING gin (
    to_tsvector(
        'simple',
        COALESCE(name, '') || ' ' ||
        COALESCE(description, '') || ' ' ||
        COALESCE(category, '') || ' ' ||
        COALESCE(brand, '') || ' ' ||
        COALESCE(country_of_origin, '') || ' ' ||
        COALESCE(embedding_source_text, '')
    )
)
WHERE is_active = true;

INSERT INTO schema_migrations (version, description)
VALUES ('V006', 'add product keyword search index')
ON CONFLICT (version) DO NOTHING;
