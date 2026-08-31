from langchain.tools import tool

from core.auth import authorize_tool, get_request_context, unauthorized_message
from core.services import (
    cart_service,
    knowledge_service,
    order_service,
    product_service,
    support_service,
)


def _tool_authorized(tool_name: str) -> str | None:
    result = authorize_tool(tool_name, get_request_context())
    if result.allowed:
        return None
    return unauthorized_message(result.reason)


@tool
def check_stock(product_name: str) -> str:
    """Use this when the user asks about stock or availability of a product. Input can be a full name, partial name, or common Indonesian product alias."""
    denied = _tool_authorized("check_stock")
    if denied:
        return denied
    return product_service.check_stock(product_name)


@tool
def check_order_status(order_id: str) -> str:
    """Use this when the user asks about order status or shipping tracking. Input: order ID (e.g. ORD001)."""
    denied = _tool_authorized("check_order_status")
    if denied:
        return denied
    return order_service.check_order_status(order_id)


@tool
def search_products(
    category: str = "",
    max_price: float = 0,
    min_price: float = 0,
    query: str = "",
    size: int = 0,
    color: str = "",
    waterproof: bool | None = None,
    sku: str = "",
    available: bool | None = None,
    min_stock: int = 0,
    soft_preferences: str = "",
) -> str:
    """Use this when the user wants to browse or filter products by structured search criteria.
    Input parameters:
    - category: product category like 'Electronics', 'Shoes', 'Clothing', 'Beauty', 'Accessories', 'Bags', 'Books' (optional)
    - max_price: maximum price in Rupiah (optional, 0 means no limit)
    - min_price: minimum price in Rupiah (optional, 0 means no limit)
    - query: raw product phrase for extraction, such as 'black waterproof hiking shoes size 42' (optional)
    - size: requested size when mentioned, such as 42 (optional)
    - color: requested color when mentioned, such as 'black' (optional)
    - waterproof: true/false when explicitly mentioned (optional)
    - sku: exact SKU or product code when mentioned (optional, hard constraint)
    - available: true when user requires in-stock/available products, false for out-of-stock searches (optional, hard constraint)
    - min_stock: minimum available stock quantity when mentioned (optional, hard constraint)
    - soft_preferences: comma-separated preferences like 'comfortable, minimalist, good for winter' (optional, soft constraints)
    Examples: user says 'show me cheap electronics under 600000' -> category='Electronics', max_price=600000.
    User says 'black waterproof hiking shoes size 42 under Rp500000' -> query='black waterproof hiking shoes size 42 under Rp500000', category='Shoes', size=42, color='black', waterproof=true, max_price=500000."""
    denied = _tool_authorized("search_products")
    if denied:
        return denied
    normalized_size = size if size and size > 0 else None
    return product_service.search_products(
        category=category,
        max_price=max_price,
        min_price=min_price,
        query=query,
        size=normalized_size,
        color=color,
        waterproof=waterproof,
        sku=sku,
        available=available,
        min_stock=min_stock,
        soft_preferences=soft_preferences,
    )


@tool
def cancel_customer_order(order_id: str) -> str:
    """Use this when the user wants to cancel an order. Only works for orders with 'Processing' or 'Awaiting Payment' status. Input: order ID (e.g. ORD002)."""
    denied = _tool_authorized("cancel_customer_order")
    if denied:
        return denied
    return order_service.cancel_order(order_id)


@tool
def update_shipping_address(order_id: str, new_address: str) -> str:
    """Use this when the user wants to change/update the shipping address of an order. Only works for orders not yet shipped. Input: order ID and the new full address."""
    denied = _tool_authorized("update_shipping_address")
    if denied:
        return denied
    return order_service.update_order_address(order_id, new_address)


@tool
def add_product_to_cart(product_name: str, quantity: int = 1) -> str:
    """Use this when the user wants to add a product to their shopping cart. Input can be a full name, partial name, or common Indonesian product alias. Call this tool before asking for clarification unless the product is truly ambiguous."""
    denied = _tool_authorized("add_product_to_cart")
    if denied:
        return denied
    return cart_service.add_to_cart(product_name, quantity)


@tool
def view_shopping_cart() -> str:
    """Use this when the user wants to see what is currently in their shopping cart."""
    denied = _tool_authorized("view_shopping_cart")
    if denied:
        return denied
    return cart_service.view_cart()


@tool
def clear_shopping_cart() -> str:
    """Use this when the user wants to empty/clear their entire shopping cart."""
    denied = _tool_authorized("clear_shopping_cart")
    if denied:
        return denied
    return cart_service.clear_cart()


@tool
def search_knowledge_base(query: str) -> str:
    """Use this when the user asks about store policies, return/refund rules, shipping info, warranty, payment methods, operating hours, loyalty program, or any general FAQ.
    Input: the user's question or keywords about store policy.
    This searches the store's official knowledge base document."""
    denied = _tool_authorized("search_knowledge_base")
    if denied:
        return denied
    return knowledge_service.search_knowledge_base(query)


@tool
def escalate_to_human(
    customer_message: str,
    reason: str = "",
    priority: str = "Normal",
    summarized_context: str = "",
    escalation_type: str = "",
) -> str:
    """Use this when the user's issue cannot be resolved by the AI, when the user explicitly asks to speak to a human, or when the user is very frustrated/angry.
    Input:
    - customer_message: the original message or complaint from the user
    - reason: brief reason why escalation is needed
    - priority: 'Low', 'Normal', 'High', or 'Urgent'
    - summarized_context: concise context summary for the human support agent
    - escalation_type: category such as fraud, legal_complaint, payment_dispute, high_value_refund, repeated_failure, low_confidence, or human_requested"""
    denied = _tool_authorized("escalate_to_human")
    if denied:
        return denied
    return support_service.create_support_ticket(
        customer_message,
        agent_summary=summarized_context or reason,
        priority=priority,
        escalation_type=escalation_type,
        escalation_reason=reason,
        summarized_context=summarized_context,
    )


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
