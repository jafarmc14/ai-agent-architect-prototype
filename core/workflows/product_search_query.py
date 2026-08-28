import re
from dataclasses import dataclass
from typing import Any


CATALOG_CATEGORY_ALIASES = {
    "accessories": "Accessories",
    "accessory": "Accessories",
    "aksesoris": "Accessories",
    "bags": "Bags",
    "bag": "Bags",
    "tas": "Bags",
    "beauty": "Beauty",
    "skincare": "Beauty",
    "perfume": "Beauty",
    "books": "Books",
    "book": "Books",
    "buku": "Books",
    "clothing": "Clothing",
    "shirt": "Clothing",
    "t-shirt": "Clothing",
    "kaos": "Clothing",
    "baju": "Clothing",
    "electronics": "Electronics",
    "electronic": "Electronics",
    "elektronik": "Electronics",
    "headphone": "Electronics",
    "keyboard": "Electronics",
    "mouse": "Electronics",
    "smartwatch": "Electronics",
    "shoes": "Shoes",
    "shoe": "Shoes",
    "sneaker": "Shoes",
    "sneakers": "Shoes",
    "sandals": "Shoes",
    "sepatu": "Shoes",
}

COLOR_ALIASES = {
    "black": "black",
    "hitam": "black",
    "white": "white",
    "putih": "white",
    "red": "red",
    "merah": "red",
    "blue": "blue",
    "biru": "blue",
    "green": "green",
    "hijau": "green",
    "brown": "brown",
    "coklat": "brown",
    "gray": "gray",
    "grey": "gray",
    "abu": "gray",
}

SOFT_CONSTRAINT_ALIASES = {
    "comfortable": "comfortable",
    "comfy": "comfortable",
    "nyaman": "comfortable",
    "minimalist": "minimalist",
    "minimalis": "minimalist",
    "good for winter": "good for winter",
    "winter": "good for winter",
    "musim dingin": "good for winter",
    "premium": "premium",
    "stylish": "stylish",
    "trendy": "stylish",
    "casual": "casual",
}


@dataclass(frozen=True)
class ProductSearchQuery:
    query: str = ""
    category: str = ""
    catalog_category: str = ""
    size: int | None = None
    color: str = ""
    waterproof: bool | None = None
    sku: str = ""
    available: bool | None = None
    min_stock: int = 0
    soft_constraints: list[str] | None = None
    min_price: float = 0
    max_price: float = 0

    @property
    def hard_constraints(self) -> dict[str, Any]:
        hard = {}
        if self.min_price > 0:
            hard["min_price"] = self.min_price
        if self.max_price > 0:
            hard["max_price"] = self.max_price
        if self.size is not None:
            hard["size"] = self.size
        if self.available is not None:
            hard["availability"] = self.available
        if self.sku:
            hard["sku"] = self.sku
        if self.min_stock > 0:
            hard["stock"] = self.min_stock
        return hard

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "category": self.category,
            "catalog_category": self.catalog_category,
            "size": self.size,
            "color": self.color,
            "waterproof": self.waterproof,
            "sku": self.sku,
            "available": self.available,
            "min_stock": self.min_stock,
            "hard_constraints": self.hard_constraints,
            "soft_constraints": self.soft_constraints or [],
            "min_price": self.min_price,
            "max_price": self.max_price,
        }

    def unsupported_filters(self) -> list[str]:
        unsupported = []
        if self.color:
            unsupported.append("color")
        if self.waterproof is not None:
            unsupported.append("waterproof")
        return unsupported

    def unsupported_hard_constraints(self) -> list[str]:
        return []


def extract_product_search_query(
    query: str = "",
    category: str = "",
    min_price: float = 0,
    max_price: float = 0,
    size: int | None = None,
    color: str = "",
    waterproof: bool | None = None,
    sku: str = "",
    available: bool | None = None,
    min_stock: int = 0,
    soft_preferences: str = "",
) -> ProductSearchQuery:
    """Extract structured product search criteria while keeping deterministic filters explicit."""
    text = " ".join(part for part in (query, category) if part).strip()

    extracted_category = category.strip()
    catalog_category = _catalog_category(text)
    if not extracted_category:
        extracted_category = catalog_category

    extracted_min_price = min_price or _extract_min_price(text)
    extracted_max_price = max_price or _extract_max_price(text)
    extracted_size = size if size is not None and size > 0 else _extract_size(text)
    extracted_color = color.strip().lower() if color else _extract_color(text)
    extracted_waterproof = waterproof if waterproof is not None else _extract_waterproof(text)
    extracted_sku = sku.strip() if sku else _extract_sku(text)
    extracted_available = available if available is not None else _extract_availability(text)
    extracted_min_stock = min_stock if min_stock > 0 else _extract_min_stock(text)
    extracted_soft_constraints = _extract_soft_constraints(" ".join([text, soft_preferences]).strip())

    return ProductSearchQuery(
        query=query.strip(),
        category=extracted_category,
        catalog_category=catalog_category or _catalog_category(extracted_category),
        size=extracted_size,
        color=extracted_color,
        waterproof=extracted_waterproof,
        sku=extracted_sku,
        available=extracted_available,
        min_stock=extracted_min_stock,
        soft_constraints=extracted_soft_constraints,
        min_price=extracted_min_price,
        max_price=extracted_max_price,
    )


def _catalog_category(text: str) -> str:
    lowered = text.lower()
    for alias, category in CATALOG_CATEGORY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return category
    return ""


def _extract_size(text: str) -> int | None:
    match = re.search(r"\b(?:size|ukuran|no\.?|nomor)\s*[:#-]?\s*(\d{1,3})\b", text, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _extract_color(text: str) -> str:
    lowered = text.lower()
    for alias, color in COLOR_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return color
    return ""


def _extract_waterproof(text: str) -> bool | None:
    lowered = text.lower()
    if re.search(r"\b(not waterproof|non-waterproof|tidak\s+(anti\s*air|tahan\s*air))\b", lowered):
        return False
    if re.search(r"\b(waterproof|anti\s*air|tahan\s*air)\b", lowered):
        return True
    return None


def _extract_sku(text: str) -> str:
    match = re.search(r"\b(?:sku|kode\s+produk)\s*[:#-]?\s*([a-z0-9-]+)\b", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).upper()


def _extract_availability(text: str) -> bool | None:
    lowered = text.lower()
    if re.search(r"\b(in stock|available|ready stock|tersedia|stok tersedia|ada stok)\b", lowered):
        return True
    if re.search(r"\b(out of stock|sold out|habis|stok habis|tidak tersedia)\b", lowered):
        return False
    return None


def _extract_min_stock(text: str) -> int:
    match = re.search(r"\b(?:stock|stok|minimum stock|min stock)\s*[:#-]?\s*(\d+)\b", text, re.IGNORECASE)
    if not match:
        return 0
    return int(match.group(1))


def _extract_soft_constraints(text: str) -> list[str]:
    lowered = text.lower()
    constraints = []
    for alias, constraint in SOFT_CONSTRAINT_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered) and constraint not in constraints:
            constraints.append(constraint)
    return constraints


def _extract_min_price(text: str) -> float:
    patterns = [
        r"\b(?:above|over|minimum|min|from|di atas|lebih dari|mulai dari)\s*(?:rp|idr)?\s*([\d.,]+)\b",
        r"\bbetween\s*(?:rp|idr)?\s*([\d.,]+)\s*(?:and|-|to)\s*(?:rp|idr)?\s*[\d.,]+\b",
        r"\bantara\s*(?:rp|idr)?\s*([\d.,]+)\s*(?:dan|-|sampai)\s*(?:rp|idr)?\s*[\d.,]+\b",
    ]
    return _extract_price_with_patterns(text, patterns)


def _extract_max_price(text: str) -> float:
    patterns = [
        r"\b(?:under|below|maximum|max|up to|di bawah|kurang dari|maksimal)\s*(?:rp|idr)?\s*([\d.,]+)\b",
        r"\bbetween\s*(?:rp|idr)?\s*[\d.,]+\s*(?:and|-|to)\s*(?:rp|idr)?\s*([\d.,]+)\b",
        r"\bantara\s*(?:rp|idr)?\s*[\d.,]+\s*(?:dan|-|sampai)\s*(?:rp|idr)?\s*([\d.,]+)\b",
    ]
    return _extract_price_with_patterns(text, patterns)


def _extract_price_with_patterns(text: str, patterns: list[str]) -> float:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _parse_price(match.group(1))
    return 0


def _parse_price(value: str) -> float:
    normalized = value.strip()
    if "." in normalized and "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif "," in normalized:
        normalized = normalized.replace(",", "")
    elif "." in normalized:
        parts = normalized.split(".")
        if all(len(part) == 3 for part in parts[1:]):
            normalized = normalized.replace(".", "")
    try:
        return float(normalized)
    except ValueError:
        return 0
