from pathlib import Path

from core.repositories import StoreRepository


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


class StoreService:
    """Business logic used by the LLM tools."""

    def __init__(self, repository: StoreRepository | None = None, knowledge_base_path: Path | None = None):
        self.repository = repository or StoreRepository()
        self.knowledge_base_path = knowledge_base_path or Path(__file__).resolve().parents[2] / "knowledge_base.txt"
        self.knowledge_base_content = ""
        if self.knowledge_base_path.exists():
            self.knowledge_base_content = self.knowledge_base_path.read_text(encoding="utf-8")

    def normalize_product_query(self, product_name: str) -> str:
        product_key = product_name.lower().strip()
        return PRODUCT_ALIASES.get(product_key, product_name)

    def check_stock(self, product_name: str) -> str:
        search_term = self.normalize_product_query(product_name)
        rows = self.repository.find_products_by_name(search_term)

        if not rows:
            return f"No products found matching '{product_name}' in the database."

        results = []
        for row in rows:
            results.append(
                f"• {row['name']} | Category: {row['category']} | Price: Rp{row['price']:,.0f} | Stock: {row['stock']} units | Origin: {row['country']}"
            )
        return "\n".join(results)

    def check_order_status(self, order_id: str) -> str:
        row = self.repository.find_order_with_product(order_id)

        if not row:
            return f"Order with ID '{order_id}' not found in the database."

        arrival = row["estimated_arrival"] if row["estimated_arrival"] else "Not yet determined"
        return (
            f"📦 Order Details — {row['id']}:\n"
            f"• Customer: {row['customer_name']}\n"
            f"• Product: {row['product_name']} (x{row['quantity']})\n"
            f"• Total: Rp{row['total_price']:,.0f}\n"
            f"• Status: {row['status']}\n"
            f"• Address: {row['shipping_address']}\n"
            f"• Order Date: {row['order_date']}\n"
            f"• Estimated Arrival: {arrival}"
        )

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

    def cancel_order(self, order_id: str) -> str:
        row = self.repository.find_order_for_update(order_id)

        if not row:
            return f"Order '{order_id}' not found in the database."

        if row["status"] in ("Completed", "Shipped"):
            return f"❌ Cannot cancel order {row['id']}. Current status is '{row['status']}'. Only orders with status 'Processing' or 'Awaiting Payment' can be cancelled."

        if row["status"] == "Cancelled":
            return f"Order {row['id']} has already been cancelled."

        self.repository.update_order_status(order_id, "Cancelled")
        return f"✅ Order {row['id']} for customer '{row['customer_name']}' has been successfully cancelled. Previous status: '{row['status']}' → New status: 'Cancelled'."

    def update_order_address(self, order_id: str, new_address: str) -> str:
        row = self.repository.find_order_for_update(order_id)

        if not row:
            return f"Order '{order_id}' not found in the database."

        if row["status"] in ("Shipped", "Completed", "Cancelled"):
            return f"❌ Cannot update address for order {row['id']}. Current status is '{row['status']}'. Address can only be changed for 'Processing' or 'Awaiting Payment' orders."

        old_address = row["shipping_address"]
        self.repository.update_order_shipping_address(order_id, new_address)
        return f"✅ Shipping address for order {row['id']} has been updated.\n• Old address: {old_address}\n• New address: {new_address}"

    def add_to_cart(self, product_name: str, quantity: int = 1, session_id: str = "default") -> str:
        search_term = self.normalize_product_query(product_name)
        rows = self.repository.find_products_by_name(search_term)

        if not rows:
            return f"Product '{product_name}' not found. Please check the product name and try again."

        if len(rows) > 1:
            names = ", ".join([row["name"] for row in rows])
            return f"Multiple products matched '{product_name}': {names}. Please be more specific."

        product = rows[0]
        if quantity > product["stock"]:
            return f"❌ Insufficient stock for '{product['name']}'. Requested: {quantity}, Available: {product['stock']} units."

        existing = self.repository.find_cart_item(session_id, product["id"])
        if existing:
            new_quantity = existing["quantity"] + quantity
            self.repository.update_cart_quantity(existing["id"], new_quantity)
        else:
            self.repository.insert_cart_item(session_id, product["id"], quantity)

        total = product["price"] * quantity
        return f"🛒 Added to cart: {product['name']} x{quantity} (Rp{total:,.0f})"

    def view_cart(self, session_id: str = "default") -> str:
        rows = self.repository.list_cart_items(session_id)

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
        deleted = self.repository.delete_cart_items(session_id)

        if deleted == 0:
            return "🛒 Cart is already empty, nothing to clear."
        return f"🗑️ Shopping cart cleared. {deleted} item(s) removed."

    def search_knowledge_base(self, query: str) -> str:
        if not self.knowledge_base_content:
            return "Knowledge base is not available at this time."

        query_lower = query.lower()
        lines = self.knowledge_base_content.split("\n")
        relevant_lines = []
        current_section = ""

        for line in lines:
            if line.startswith("---") and line.endswith("---"):
                current_section = line
            if any(keyword in line.lower() for keyword in query_lower.split()):
                if current_section and current_section not in relevant_lines:
                    relevant_lines.append(current_section)
                relevant_lines.append(line)

        if not relevant_lines:
            return f"No exact keyword match found for '{query}'. Here is the full knowledge base for reference:\n\n{self.knowledge_base_content}"

        return f"Relevant store policy information for '{query}':\n" + "\n".join(relevant_lines)

    def create_support_ticket(self, customer_message: str, agent_summary: str = "", priority: str = "Normal") -> str:
        ticket_id = self.repository.insert_support_ticket(customer_message, agent_summary, priority)
        return f"🎫 Support ticket #{ticket_id} created successfully (Priority: {priority}). A human agent will review your case within 1x24 hours."


store_service = StoreService()
