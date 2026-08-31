from core.services.cart_service import cart_service
from core.services.knowledge_service import knowledge_service
from core.services.order_service import order_service
from core.services.product_service import product_service
from core.services.support_service import support_service


class StoreService:
    """Compatibility facade for domain-specific services."""

    def check_stock(self, product_name: str) -> str:
        return product_service.check_stock(product_name)

    def search_products(self, category: str = "", max_price: float = 0, min_price: float = 0) -> str:
        return product_service.search_products(category, max_price, min_price)

    def check_order_status(self, order_id: str) -> str:
        return order_service.check_order_status(order_id)

    def cancel_order(self, order_id: str, confirmed: bool = False, idempotency_key: str = "", request_id: str = "") -> str:
        return order_service.cancel_order(order_id, confirmed, idempotency_key, request_id)

    def update_order_address(
        self,
        order_id: str,
        new_address: str,
        confirmed: bool = False,
        idempotency_key: str = "",
        request_id: str = "",
    ) -> str:
        return order_service.update_order_address(order_id, new_address, confirmed, idempotency_key, request_id)

    def add_to_cart(
        self,
        product_name: str,
        quantity: int = 1,
        session_id: str = "default",
        confirmed: bool = False,
        idempotency_key: str = "",
        request_id: str = "",
    ) -> str:
        return cart_service.add_to_cart(product_name, quantity, session_id, confirmed, idempotency_key, request_id)

    def view_cart(self, session_id: str = "default") -> str:
        return cart_service.view_cart(session_id)

    def clear_cart(self, session_id: str = "default", confirmed: bool = False, idempotency_key: str = "", request_id: str = "") -> str:
        return cart_service.clear_cart(session_id, confirmed, idempotency_key, request_id)

    def search_knowledge_base(self, query: str) -> str:
        return knowledge_service.search_knowledge_base(query)

    def create_support_ticket(self, customer_message: str, agent_summary: str = "", priority: str = "Normal") -> str:
        return support_service.create_support_ticket(customer_message, agent_summary, priority)


store_service = StoreService()
