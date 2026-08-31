from configs import get_settings
from core.auth import get_request_context, order_owner_filter_user_id, unauthorized_message
from core.repositories import OrderRepository
from core.services.write_action_service import build_idempotency_key, write_action_service


class OrderService:
    """Business logic for order lookup and controlled order mutations."""

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
            f"Order Details - {row['id']}:\n"
            f"- Product: {row['product_name']} (x{row['quantity']})\n"
            f"- Total: Rp{row['total_price']:,.0f}\n"
            f"- Status: {row['status']}\n"
            f"- Shipping address: saved on order\n"
            f"- Order Date: {row['order_date']}\n"
            f"- Estimated Arrival: {arrival}"
        )

    def cancel_order(
        self,
        order_id: str,
        confirmed: bool = False,
        idempotency_key: str = "",
        request_id: str = "",
    ) -> str:
        if not get_settings().high_risk_write_actions_enabled:
            return (
                "Order cancellation is currently disabled. "
                "High-risk write actions require business approval before activation."
            )

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
            return (
                f"Cannot cancel order {row['id']}. Current status is '{row['status']}'. "
                "Only orders with status 'Processing' or 'Awaiting Payment' can be cancelled."
            )

        if row["status"] == "Cancelled":
            return f"Order {row['id']} has already been cancelled."

        payload = {"order_id": row["id"], "new_status": "Cancelled"}
        idempotency_key = idempotency_key or build_idempotency_key(
            context,
            "order.cancel",
            "order",
            row["id"],
            payload,
        )
        existing_response = write_action_service.find_existing_response(idempotency_key, context)
        if existing_response:
            return existing_response
        if not confirmed:
            return write_action_service.prepare_confirmation(
                action="order.cancel",
                resource_type="order",
                resource_id=row["id"],
                payload=payload,
                prompt=f"Cancel order {row['id']}? Current status: {row['status']}.",
            )

        if hasattr(self.repository, "update_order_status_transactional"):
            locked_row = self.repository.update_order_status_transactional(order_id, "Cancelled", user_id=owner_user_id)
            if not locked_row:
                return f"Order '{order_id}' was not found for the authenticated user."
            if locked_row.get("blocked"):
                return (
                    f"Cannot cancel order {locked_row['id']}. Current status is '{locked_row['status']}'. "
                    "Only orders with status 'Processing' or 'Awaiting Payment' can be cancelled."
                )
            row = locked_row
        else:
            self.repository.update_order_status(order_id, "Cancelled", user_id=owner_user_id)
        response = (
            f"Order {row['id']} has been successfully cancelled. "
            f"Previous status: '{row['status']}' -> New status: 'Cancelled'."
        )
        write_action_service.record_success(
            action="order.cancel",
            resource_type="order",
            resource_id=row["id"],
            old_value={"status": row["status"]},
            new_value={"status": "Cancelled"},
            response=response,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return response

    def update_order_address(
        self,
        order_id: str,
        new_address: str,
        confirmed: bool = False,
        idempotency_key: str = "",
        request_id: str = "",
    ) -> str:
        if not get_settings().high_risk_write_actions_enabled:
            return (
                "Address update is currently disabled. "
                "High-risk write actions require business approval before activation."
            )

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
            return (
                f"Cannot update address for order {row['id']}. Current status is '{row['status']}'. "
                "Address can only be changed for 'Processing' or 'Awaiting Payment' orders."
            )

        payload = {"order_id": row["id"], "new_address": new_address}
        idempotency_key = idempotency_key or build_idempotency_key(
            context,
            "order.update_shipping_address",
            "order",
            row["id"],
            payload,
        )
        existing_response = write_action_service.find_existing_response(idempotency_key, context)
        if existing_response:
            return existing_response
        if not confirmed:
            return write_action_service.prepare_confirmation(
                action="order.update_shipping_address",
                resource_type="order",
                resource_id=row["id"],
                payload=payload,
                prompt=f"Update shipping address for order {row['id']}?",
            )

        if hasattr(self.repository, "update_order_shipping_address_transactional"):
            locked_row = self.repository.update_order_shipping_address_transactional(
                order_id,
                new_address,
                user_id=owner_user_id,
            )
            if not locked_row:
                return f"Order '{order_id}' was not found for the authenticated user."
            if locked_row.get("blocked"):
                return (
                    f"Cannot update address for order {locked_row['id']}. Current status is '{locked_row['status']}'. "
                    "Address can only be changed for 'Processing' or 'Awaiting Payment' orders."
                )
            row = locked_row
        else:
            self.repository.update_order_shipping_address(order_id, new_address, user_id=owner_user_id)
        response = f"Shipping address for order {row['id']} has been updated to the address provided."
        write_action_service.record_success(
            action="order.update_shipping_address",
            resource_type="order",
            resource_id=row["id"],
            old_value={"shipping_address": row["shipping_address"]},
            new_value={"shipping_address": new_address},
            response=response,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return response


order_service = OrderService()
