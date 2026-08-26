from langchain.tools import tool

from core.services import store_service


@tool
def check_stock(product_name: str) -> str:
    """Use this when the user asks about stock or availability of a product. Input can be a full name, partial name, or common Indonesian product alias."""
    return store_service.check_stock(product_name)


@tool
def check_order_status(order_id: str) -> str:
    """Use this when the user asks about order status or shipping tracking. Input: order ID (e.g. ORD001)."""
    return store_service.check_order_status(order_id)


@tool
def search_products(category: str = "", max_price: float = 0, min_price: float = 0) -> str:
    """Use this when the user wants to browse or filter products by category and/or price range.
    Input parameters:
    - category: product category like 'Electronics', 'Shoes', 'Clothing', 'Beauty', 'Accessories', 'Bags', 'Books' (optional)
    - max_price: maximum price in Rupiah (optional, 0 means no limit)
    - min_price: minimum price in Rupiah (optional, 0 means no limit)
    Examples: user says 'show me cheap electronics under 600000' -> category='Electronics', max_price=600000"""
    return store_service.search_products(category, max_price, min_price)


@tool
def cancel_customer_order(order_id: str) -> str:
    """Use this when the user wants to cancel an order. Only works for orders with 'Processing' or 'Awaiting Payment' status. Input: order ID (e.g. ORD002)."""
    return store_service.cancel_order(order_id)


@tool
def update_shipping_address(order_id: str, new_address: str) -> str:
    """Use this when the user wants to change/update the shipping address of an order. Only works for orders not yet shipped. Input: order ID and the new full address."""
    return store_service.update_order_address(order_id, new_address)


@tool
def add_product_to_cart(product_name: str, quantity: int = 1) -> str:
    """Use this when the user wants to add a product to their shopping cart. Input can be a full name, partial name, or common Indonesian product alias. Call this tool before asking for clarification unless the product is truly ambiguous."""
    return store_service.add_to_cart(product_name, quantity)


@tool
def view_shopping_cart() -> str:
    """Use this when the user wants to see what is currently in their shopping cart."""
    return store_service.view_cart()


@tool
def clear_shopping_cart() -> str:
    """Use this when the user wants to empty/clear their entire shopping cart."""
    return store_service.clear_cart()


@tool
def search_knowledge_base(query: str) -> str:
    """Use this when the user asks about store policies, return/refund rules, shipping info, warranty, payment methods, operating hours, loyalty program, or any general FAQ.
    Input: the user's question or keywords about store policy.
    This searches the store's official knowledge base document."""
    return store_service.search_knowledge_base(query)


@tool
def escalate_to_human(customer_message: str, reason: str = "", priority: str = "Normal") -> str:
    """Use this when the user's issue cannot be resolved by the AI, when the user explicitly asks to speak to a human, or when the user is very frustrated/angry.
    Input:
    - customer_message: the original message or complaint from the user
    - reason: brief summary of why escalation is needed (written by the AI agent)
    - priority: 'Low', 'Normal', 'High', or 'Urgent'"""
    return store_service.create_support_ticket(customer_message, reason, priority)


tools = [
    check_stock,
    check_order_status,
    search_products,
    cancel_customer_order,
    update_shipping_address,
    add_product_to_cart,
    view_shopping_cart,
    clear_shopping_cart,
    search_knowledge_base,
    escalate_to_human,
]
tools_by_name = {t.name: t for t in tools}
