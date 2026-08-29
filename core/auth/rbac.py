from dataclasses import dataclass
from enum import Enum

from core.auth.request_context import RequestContext


class Role(str, Enum):
    ANONYMOUS = "anonymous"
    CUSTOMER = "customer"
    SUPPORT_AGENT = "support_agent"
    MANAGER = "manager"
    ADMIN = "admin"


ROLE_ACCESS_LEVEL = {
    Role.ANONYMOUS: "public",
    Role.CUSTOMER: "public",
    Role.SUPPORT_AGENT: "internal",
    Role.MANAGER: "restricted",
    Role.ADMIN: "restricted",
}

ROLE_DEPARTMENT = {
    Role.ANONYMOUS: "public",
    Role.CUSTOMER: "public",
    Role.SUPPORT_AGENT: "support",
    Role.MANAGER: "management",
    Role.ADMIN: "admin",
}

TOOL_PERMISSIONS = {
    "check_stock": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "search_products": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "search_knowledge_base": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "check_order_status": {Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "add_product_to_cart": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "view_shopping_cart": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "clear_shopping_cart": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "cancel_customer_order": {Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "update_shipping_address": {Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
    "escalate_to_human": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
}

WORKFLOW_PERMISSIONS = {
    "rag_policy": TOOL_PERMISSIONS["search_knowledge_base"],
    "product_search": TOOL_PERMISSIONS["search_products"],
    "order_status": TOOL_PERMISSIONS["check_order_status"],
    "agent_loop": {Role.ANONYMOUS, Role.CUSTOMER, Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN},
}

CUSTOMER_OWNED_RESOURCE_ROLES = {Role.CUSTOMER}
STAFF_ROLES = {Role.SUPPORT_AGENT, Role.MANAGER, Role.ADMIN}


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    role: Role
    reason: str


def role_from_context(context: RequestContext) -> Role:
    if not context.user:
        return Role.ANONYMOUS
    raw_role = (context.user.role or Role.CUSTOMER.value).strip().lower()
    try:
        return Role(raw_role)
    except ValueError:
        return Role.CUSTOMER


def authorize_tool(tool_name: str, context: RequestContext) -> AuthorizationResult:
    role = role_from_context(context)
    allowed_roles = TOOL_PERMISSIONS.get(tool_name, set())
    if role in allowed_roles:
        return AuthorizationResult(True, role, "allowed")
    return AuthorizationResult(False, role, f"role '{role.value}' cannot use tool '{tool_name}'")


def authorize_workflow(workflow: str, context: RequestContext) -> AuthorizationResult:
    role = role_from_context(context)
    allowed_roles = WORKFLOW_PERMISSIONS.get(workflow, set())
    if role in allowed_roles:
        return AuthorizationResult(True, role, "allowed")
    return AuthorizationResult(False, role, f"role '{role.value}' cannot use workflow '{workflow}'")


def order_owner_filter_user_id(context: RequestContext) -> str | None:
    role = role_from_context(context)
    if role in CUSTOMER_OWNED_RESOURCE_ROLES:
        return context.user_id
    if role in STAFF_ROLES:
        return None
    return "__unauthorized__"


def knowledge_access_level(context: RequestContext) -> str:
    return ROLE_ACCESS_LEVEL[role_from_context(context)]


def knowledge_department(context: RequestContext) -> str:
    return ROLE_DEPARTMENT[role_from_context(context)]


def unauthorized_message(reason: str) -> str:
    return f"Access denied. {reason}."
