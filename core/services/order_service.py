from core.auth import get_request_context, order_owner_filter_user_id, unauthorized_message
from core.repositories import OrderRepository


class OrderService:
    """Business logic for order lookup and order mutations."""

    def __init__(self, repository: OrderRepository | None = None):
        self.repository = repository or OrderRepository()

    def check_order_status(self, order_id: str) -> str:
        context = get_request_context()
        owner_user_id = order_owner_filter_user_id(context)
        if owner_user_id == "__unauthorized__":
            return unauthorized_message("Authentication is required to access order data")
        row = self.repository.find_order_with_product(order_id, user_id=owner_user_id)

        if not row:
            if context.is_authenticated:
                return f"Order with ID '{order_id}' was not found for the authenticated user."
            return f"Order with ID '{order_id}' not found in the database."

        arrival = row["estimated_arrival"] if row["estimated_arrival"] else "Not yet determined"
        return (
            f"📦 Order Details — {row['id']}:\n"
            f"• Product: {row['product_name']} (x{row['quantity']})\n"
            f"• Total: Rp{row['total_price']:,.0f}\n"
            f"• Status: {row['status']}\n"
            f"• Shipping address: saved on order\n"
            f"• Order Date: {row['order_date']}\n"
            f"• Estimated Arrival: {arrival}"
        )

    def cancel_order(self, order_id: str) -> str:
        context = get_request_context()
        owner_user_id = order_owner_filter_user_id(context)
        if owner_user_id == "__unauthorized__":
            return unauthorized_message("Authentication is required to modify order data")
        row = self.repository.find_order_for_update(order_id, user_id=owner_user_id)

        if not row:
            if context.is_authenticated:
                return f"Order '{order_id}' was not found for the authenticated user."
            return f"Order '{order_id}' not found in the database."

        if row["status"] in ("Completed", "Shipped"):
            return f"❌ Cannot cancel order {row['id']}. Current status is '{row['status']}'. Only orders with status 'Processing' or 'Awaiting Payment' can be cancelled."

        if row["status"] == "Cancelled":
            return f"Order {row['id']} has already been cancelled."

        self.repository.update_order_status(order_id, "Cancelled", user_id=owner_user_id)
        return f"✅ Order {row['id']} has been successfully cancelled. Previous status: '{row['status']}' → New status: 'Cancelled'."

    def update_order_address(self, order_id: str, new_address: str) -> str:
        context = get_request_context()
        owner_user_id = order_owner_filter_user_id(context)
        if owner_user_id == "__unauthorized__":
            return unauthorized_message("Authentication is required to modify order data")
        row = self.repository.find_order_for_update(order_id, user_id=owner_user_id)

        if not row:
            if context.is_authenticated:
                return f"Order '{order_id}' was not found for the authenticated user."
            return f"Order '{order_id}' not found in the database."

        if row["status"] in ("Shipped", "Completed", "Cancelled"):
            return f"❌ Cannot update address for order {row['id']}. Current status is '{row['status']}'. Address can only be changed for 'Processing' or 'Awaiting Payment' orders."

        self.repository.update_order_shipping_address(order_id, new_address, user_id=owner_user_id)
        return f"✅ Shipping address for order {row['id']} has been updated to the address provided."


order_service = OrderService()
