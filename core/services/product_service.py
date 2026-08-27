from core.repositories import ProductRepository


PRODUCT_ALIASES = {
    "nike shoes": "Nike",
    "nike shoe": "Nike",
    "sepatu nike": "Nike",
    "kaos hitam": "Black Plain T-Shirt",
    "kaos polos hitam": "Black Plain T-Shirt",
    "baju hitam": "Black Plain T-Shirt",
    "t-shirt hitam": "Black Plain T-Shirt",
    "tas eiger": "Eiger",
    "headphone sony": "Sony",
    "sony headphone": "Sony",
    "sony headphones": "Sony",
    "jam casio": "Casio",
}


def normalize_product_query(product_name: str) -> str:
    product_key = product_name.lower().strip()
    return PRODUCT_ALIASES.get(product_key, product_name)


class ProductService:
    """Business logic for product lookup and recommendations."""

    def __init__(self, repository: ProductRepository | None = None):
        self.repository = repository or ProductRepository()

    def check_stock(self, product_name: str) -> str:
        search_term = normalize_product_query(product_name)
        rows = self.repository.find_products_by_name(search_term)

        if not rows:
            return f"No products found matching '{product_name}' in the database."

        results = []
        for row in rows:
            results.append(
                f"• {row['name']} | Category: {row['category']} | Price: Rp{row['price']:,.0f} | Stock: {row['stock']} units | Origin: {row['country']}"
            )
        return "\n".join(results)

    def search_products(self, category: str = "", max_price: float = 0, min_price: float = 0) -> str:
        rows = self.repository.find_products_by_filter(category, max_price, min_price)

        if not rows:
            filters = []
            if category:
                filters.append(f"category='{category}'")
            if min_price > 0:
                filters.append(f"min_price=Rp{min_price:,.0f}")
            if max_price > 0:
                filters.append(f"max_price=Rp{max_price:,.0f}")
            return f"No products found matching filters: {', '.join(filters)}."

        results = [f"Found {len(rows)} product(s):"]
        for row in rows:
            results.append(
                f"• {row['name']} | Category: {row['category']} | Price: Rp{row['price']:,.0f} | Stock: {row['stock']} units | Origin: {row['country']}"
            )
        return "\n".join(results)


product_service = ProductService()
