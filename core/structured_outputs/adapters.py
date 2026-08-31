from typing import Any

from core.auth import AuthorizationResult, RequestContext, knowledge_access_level
from core.security import detect_prompt_injection, tool_names_for_user_input, validate_tool_call
from core.structured_outputs.schemas import (
    FilterOutput,
    IntentOutput,
    PolicyDecisionOutput,
    RoutingOutput,
    ToolArgumentsOutput,
)
from core.workflows import classify_intent, extract_product_search_query, route_intent


def build_intent_output(user_input: str) -> IntentOutput:
    intent = classify_intent(user_input)
    security_flags = _security_flags(user_input)
    return IntentOutput(
        intent=intent.value,
        confidence=1.0 if intent.value != "UNKNOWN" else 0.5,
        language=_detect_language(user_input),
        requires_tools=_intent_requires_tools(intent.value),
        security_flags=security_flags,
    )


def build_filter_output(
    query: str = "",
    category: str = "",
    min_price: float = 0,
    max_price: float = 0,
    size: int | None = None,
    color: str = "",
    waterproof: bool | None = None,
    sku: str = "",
    available: bool | None = None,
    min_stock: int = 0,
    soft_preferences: str = "",
) -> FilterOutput:
    product_query = extract_product_search_query(
        query=query,
        category=category,
        min_price=min_price,
        max_price=max_price,
        size=size,
        color=color,
        waterproof=waterproof,
        sku=sku,
        available=available,
        min_stock=min_stock,
        soft_preferences=soft_preferences,
    )
    return FilterOutput(**product_query.to_dict())


def build_routing_output(user_input: str, context: RequestContext) -> RoutingOutput:
    decision = route_intent(user_input)
    exposed_tools = sorted(tool_names_for_user_input(user_input, context)) if decision.use_agent_loop else []
    return RoutingOutput(
        intent=decision.intent.value,
        workflow=decision.workflow,
        use_agent_loop=decision.use_agent_loop,
        reason=decision.reason,
        exposed_tools=exposed_tools,
        security_flags=_security_flags(user_input),
    )


def build_tool_arguments_output(
    tool_name: str,
    arguments: dict[str, Any],
    exposed_tool_names: set[str],
    context: RequestContext,
) -> ToolArgumentsOutput:
    validation = validate_tool_call(tool_name, arguments, exposed_tool_names, context)
    return ToolArgumentsOutput(
        tool_name=tool_name,
        arguments=arguments,
        validation_pass=validation.allowed,
        validation_reason=validation.reason,
    )


def build_policy_decision_output(
    authorization: AuthorizationResult,
    context: RequestContext,
    required_role: str = "",
) -> PolicyDecisionOutput:
    return PolicyDecisionOutput(
        decision="allow" if authorization.allowed else "deny",
        allowed=authorization.allowed,
        reason=authorization.reason,
        required_role=required_role,
        access_level=knowledge_access_level(context),
        security_flags=[],
    )


def _security_flags(user_input: str) -> list[str]:
    return sorted({finding.category for finding in detect_prompt_injection(user_input)})


def _intent_requires_tools(intent: str) -> bool:
    return intent in {
        "PRODUCT_SEARCH",
        "PRODUCT_INFO",
        "PRODUCT_COMPARE",
        "ORDER_STATUS",
        "RETURN_POLICY",
        "CART",
        "TRANSACTION",
        "COMPLAINT",
        "ESCALATION",
        "GENERAL_FAQ",
    }


def _detect_language(user_input: str) -> str:
    lowered = user_input.lower()
    indonesian_markers = {"apa", "apakah", "saya", "pesanan", "produk", "stok", "keranjang", "tolong"}
    english_markers = {"what", "how", "my", "order", "product", "stock", "cart", "please"}
    words = set(lowered.replace("?", " ").replace(",", " ").split())
    if len(words & indonesian_markers) > len(words & english_markers):
        return "Indonesian"
    if len(words & english_markers) > len(words & indonesian_markers):
        return "English"
    return "unknown"
