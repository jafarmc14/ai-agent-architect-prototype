from typing import Any


RELEVANT_PRODUCT_FIELDS = (
    "name",
    "description",
    "category",
    "brand",
    "country_of_origin",
    "variant_names",
    "variant_attributes",
)

EXCLUDED_PRODUCT_FIELDS = (
    "id",
    "sku",
    "base_price",
    "currency",
    "stock",
    "quantity_on_hand",
    "quantity_reserved",
    "created_at",
    "updated_at",
)


def build_product_embedding_text(product: dict[str, Any]) -> str:
    """Build semantic product text without factual filter fields like price, stock, SKU, or IDs."""
    parts = []

    for field in RELEVANT_PRODUCT_FIELDS:
        value = product.get(field)
        if value in (None, "", [], {}):
            continue
        parts.append(f"{field}: {_format_value(value)}")

    return "\n".join(parts)


def _format_value(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))
    if isinstance(value, list):
        return ", ".join(_format_value(item) for item in value if item not in (None, "", [], {}))
    return str(value)
