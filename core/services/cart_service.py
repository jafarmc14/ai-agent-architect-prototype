from core.repositories import CartRepository, ProductRepository
from core.services.product_service import normalize_product_query


class CartService:
    """Business logic for shopping cart operations."""

    def __init__(
        self,
        cart_repository: CartRepository | None = None,
        product_repository: ProductRepository | None = None,
    ):
        self.cart_repository = cart_repository or CartRepository()
        self.product_repository = product_repository or ProductRepository()

    def add_to_cart(self, product_name: str, quantity: int = 1, session_id: str = "default") -> str:
        search_term = normalize_product_query(product_name)
        rows = self.product_repository.find_products_by_name(search_term)

        if not rows:
            return f"Product '{product_name}' not found. Please check the product name and try again."

        if len(rows) > 1:
            names = ", ".join([row["name"] for row in rows])
            return f"Multiple products matched '{product_name}': {names}. Please be more specific."

        product = rows[0]
        if quantity > product["stock"]:
            return f"❌ Insufficient stock for '{product['name']}'. Requested: {quantity}, Available: {product['stock']} units."

        existing = self.cart_repository.find_cart_item(session_id, product["id"])
        if existing:
            new_quantity = existing["quantity"] + quantity
            self.cart_repository.update_cart_quantity(existing["id"], new_quantity)
        else:
            self.cart_repository.insert_cart_item(session_id, product["id"], quantity)

        total = product["price"] * quantity
        return f"🛒 Added to cart: {product['name']} x{quantity} (Rp{total:,.0f})"

    def view_cart(self, session_id: str = "default") -> str:
        rows = self.cart_repository.list_cart_items(session_id)

        if not rows:
            return "🛒 Your shopping cart is empty."

        results = ["🛒 Your Shopping Cart:"]
        grand_total = 0
        for row in rows:
            results.append(f"• {row['name']} x{row['quantity']} — Rp{row['subtotal']:,.0f}")
            grand_total += row["subtotal"]
        results.append(f"\n💰 Grand Total: Rp{grand_total:,.0f}")
        return "\n".join(results)

    def clear_cart(self, session_id: str = "default") -> str:
        deleted = self.cart_repository.delete_cart_items(session_id)

        if deleted == 0:
            return "🛒 Cart is already empty, nothing to clear."
        return f"🗑️ Shopping cart cleared. {deleted} item(s) removed."


cart_service = CartService()
