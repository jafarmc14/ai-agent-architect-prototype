from configs import get_settings
from core.auth import get_request_context, order_owner_filter_user_id, unauthorized_message
from core.repositories import OrderRepository
from core.services.write_action_service import build_idempotency_key, write_action_service
from core.services.action_approvals import controlled_mutation
from core.companies import money
from core.auth import authorize_tool


class OrderService:
    """Business logic for order lookup and controlled order mutations."""

    def __init__(self, repository: OrderRepository | None = None):
        self.repository = repository or OrderRepository()

    def list_my_orders(self):
        context = get_request_context()
        if context.role != "customer" or not context.user_id:
            raise PermissionError("Customer login is required to view your orders")
        return self.repository.list_orders_for_user(context.user_id)

    def action_availability(self, order_id: str) -> dict:
        """Return customer-facing action availability without changing the order."""
        context = get_request_context()
        actions = {}
        if not context.is_authenticated:
            reason = "Please sign in to manage an order."
            return {"order_id": order_id, "status": None, "actions": {
                name: {"available": False, "reason": reason}
                for name in ("cancel", "update_address")}}
        owner_user_id = order_owner_filter_user_id(context)
        row = self.repository.find_order_for_update(order_id, user_id=owner_user_id)
        status = row["status"] if row else None
        for name, tool in (("cancel", "cancel_customer_order"),
                           ("update_address", "update_shipping_address")):
            authorization = authorize_tool(tool, context)
            if not row:
                reason = "This order was not found for your account."
            elif status not in ("Processing", "Awaiting Payment"):
                if name == "cancel" and status == "Cancelled":
                    reason = "This order has already been cancelled."
                elif name == "cancel":
                    reason = f"Cannot cancel this order because it is {status}. Only Awaiting Payment or Processing orders can be cancelled."
                else:
                    reason = f"Cannot change the shipping address because this order is {status}. Only Awaiting Payment or Processing orders can be changed."
            elif not authorization.allowed:
                reason = ("This store does not offer this action through chat."
                          if "company" in authorization.reason else "Your account cannot use this action.")
            elif not get_settings().high_risk_write_actions_enabled:
                reason = "Order changes are currently unavailable through chat. Please contact support."
            else:
                reason = "You will need to confirm this request. A different manager or admin must then approve it."
            actions[name] = {"available": reason.startswith("You will need"), "reason": reason}
        return {"order_id": order_id, "status": status, "actions": actions}

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
            f"- Total: {money(row['total_price'])}\n"
            f"- Status: {row['status']}\n"
            f"- Shipping address: saved on order\n"
            f"- Order Date: {row['order_date']}\n"
            f"- Estimated Arrival: {arrival}"
        )

    @controlled_mutation("order.cancel")
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

    @controlled_mutation("order.update_shipping_address")
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
