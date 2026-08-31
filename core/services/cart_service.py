from core.auth import get_request_context
from core.repositories import CartRepository, ProductRepository
from core.services.product_service import normalize_product_query
from core.services.write_action_service import build_idempotency_key, write_action_service


class CartService:
    """Business logic for shopping cart operations."""

    def __init__(
        self,
        cart_repository: CartRepository | None = None,
        product_repository: ProductRepository | None = None,
    ):
        self.cart_repository = cart_repository or CartRepository()
        self.product_repository = product_repository or ProductRepository()

    def add_to_cart(
        self,
        product_name: str,
        quantity: int = 1,
        session_id: str = "default",
        confirmed: bool = False,
        idempotency_key: str = "",
        request_id: str = "",
    ) -> str:
        context = get_request_context()
        session_id = f"user:{context.user_id}" if context.user_id else (context.session_id or session_id)
        search_term = normalize_product_query(product_name)
        rows = self.product_repository.find_products_by_name(search_term)

        if not rows:
            return f"Product '{product_name}' not found. Please check the product name and try again."

        if len(rows) > 1:
            names = ", ".join([row["name"] for row in rows])
            return f"Multiple products matched '{product_name}': {names}. Please be more specific."

        product = rows[0]
        if quantity > product["stock"]:
            return (
                f"Insufficient stock for '{product['name']}'. "
                f"Requested: {quantity}, Available: {product['stock']} units."
            )

        payload = {"product_name": product_name, "resolved_product_name": product["name"], "quantity": quantity}
        idempotency_key = idempotency_key or build_idempotency_key(
            context,
            "cart.add_item",
            "product",
            str(product["id"]),
            payload,
        )
        existing_response = write_action_service.find_existing_response(idempotency_key, context)
        if existing_response:
            return existing_response

        total = product["price"] * quantity
        if not confirmed:
            return write_action_service.prepare_confirmation(
                action="cart.add_item",
                resource_type="product",
                resource_id=str(product["id"]),
                payload=payload,
                prompt=f"Add {product['name']} x{quantity} to the cart for Rp{total:,.0f}?",
            )

        if hasattr(self.cart_repository, "add_item_transactional"):
            mutation = self.cart_repository.add_item_transactional(session_id, product["id"], quantity, context.user_id)
            old_value = {"quantity": mutation["old_quantity"]}
            new_quantity = mutation["new_quantity"]
        else:
            existing = self.cart_repository.find_cart_item(session_id, product["id"], user_id=context.user_id)
            old_value = {"quantity": existing["quantity"]} if existing else {"quantity": 0}
            if existing:
                new_quantity = existing["quantity"] + quantity
                self.cart_repository.update_cart_quantity(existing["id"], new_quantity)
            else:
                new_quantity = quantity
                self.cart_repository.insert_cart_item(session_id, product["id"], quantity, user_id=context.user_id)

        response = f"Added to cart: {product['name']} x{quantity} (Rp{total:,.0f})"
        write_action_service.record_success(
            action="cart.add_item",
            resource_type="product",
            resource_id=str(product["id"]),
            old_value=old_value,
            new_value={"quantity": new_quantity, "added_quantity": quantity, "product_name": product["name"]},
            response=response,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return response

    def view_cart(self, session_id: str = "default") -> str:
        context = get_request_context()
        session_id = f"user:{context.user_id}" if context.user_id else (context.session_id or session_id)
        rows = self.cart_repository.list_cart_items(session_id, user_id=context.user_id)

        if not rows:
            return "Your shopping cart is empty."

        results = ["Your Shopping Cart:"]
        grand_total = 0
        for row in rows:
            results.append(f"- {row['name']} x{row['quantity']} - Rp{row['subtotal']:,.0f}")
            grand_total += row["subtotal"]
        results.append(f"\nGrand Total: Rp{grand_total:,.0f}")
        return "\n".join(results)

    def clear_cart(
        self,
        session_id: str = "default",
        confirmed: bool = False,
        idempotency_key: str = "",
        request_id: str = "",
    ) -> str:
        context = get_request_context()
        session_id = f"user:{context.user_id}" if context.user_id else (context.session_id or session_id)
        rows = self.cart_repository.list_cart_items(session_id, user_id=context.user_id)
        item_count = sum(row["quantity"] for row in rows)
        payload = {"session_id": session_id, "item_count": item_count}
        idempotency_key = idempotency_key or build_idempotency_key(
            context,
            "cart.clear",
            "shopping_cart",
            session_id,
            payload,
        )
        existing_response = write_action_service.find_existing_response(idempotency_key, context)
        if existing_response:
            return existing_response

        if not confirmed:
            return write_action_service.prepare_confirmation(
                action="cart.clear",
                resource_type="shopping_cart",
                resource_id=session_id,
                payload=payload,
                prompt=f"Remove {item_count} item(s) from the cart?",
            )

        if hasattr(self.cart_repository, "clear_cart_transactional"):
            mutation = self.cart_repository.clear_cart_transactional(session_id, context.user_id)
            deleted = mutation["deleted"]
            rows = mutation["items"]
        else:
            deleted = self.cart_repository.delete_cart_items(session_id, user_id=context.user_id)
        if deleted == 0:
            return "Cart is already empty, nothing to clear."

        response = f"Shopping cart cleared. {deleted} item(s) removed."
        write_action_service.record_success(
            action="cart.clear",
            resource_type="shopping_cart",
            resource_id=session_id,
            old_value={"items": [{"name": row["name"], "quantity": row["quantity"]} for row in rows]},
            new_value={"items": []},
            response=response,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return response


cart_service = CartService()
