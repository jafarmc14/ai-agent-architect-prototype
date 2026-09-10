from pathlib import Path

from configs import get_settings
from core.repositories.postgres_connection import get_postgres_connection
from core.services.production_metrics import fingerprint


def current_fingerprints(tenant_id):
    with get_postgres_connection() as conn:
        catalog = conn.execute("""SELECT id, sku, name, description, category, base_price, is_active, metadata
                               FROM products WHERE tenant_id = %s ORDER BY id""", (tenant_id,)).fetchall()
        variants = conn.execute("""SELECT id, product_id, sku, attributes, price, is_active FROM product_variants
                                WHERE tenant_id = %s ORDER BY id""", (tenant_id,)).fetchall()
        stock = conn.execute("""SELECT id, quantity_on_hand, quantity_reserved FROM inventory
                             WHERE tenant_id = %s ORDER BY id""", (tenant_id,)).fetchall()
        documents = conn.execute("""SELECT to_jsonb(d) AS document,
                                 (status = 'active' AND superseded_by IS NULL
                                  AND (effective_date IS NULL OR effective_date <= CURRENT_DATE)
                                  AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)) AS effective_now
                                 FROM documents d
                                 WHERE tenant_id = %s ORDER BY id""", (tenant_id,)).fetchall()
        chunks = conn.execute("""SELECT id, content FROM document_chunks WHERE tenant_id = %s ORDER BY id""", (tenant_id,)).fetchall()
    root = Path(__file__).resolve().parents[2]
    files = sorted(path for folder in ("services", "workflows", "security", "auth", "prompts")
                   for path in (root / "core" / folder).rglob("*") if path.suffix in {".py", ".json", ".txt", ".md"})
    rules = {str(path.relative_to(root)): fingerprint(path.read_text(encoding="utf-8")) for path in files}
    settings = get_settings()
    rules["high_risk_write_actions_enabled"] = settings.high_risk_write_actions_enabled
    return {"catalog": fingerprint([catalog, variants]), "inventory": fingerprint(stock),
            "policies": fingerprint([documents, chunks]), "business_rules": fingerprint(rules)}
