from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import (  # noqa: E402
    AuthenticatedUser,
    RequestContext,
    Role,
    authorize_tool,
    authorize_workflow,
    get_request_context,
    knowledge_access_level,
    order_owner_filter_user_id,
    request_context,
)
from core.services.knowledge_service import KnowledgeService  # noqa: E402


class StaticEmbeddingProvider:
    def embed_text(self, text):
        return [0.1] * 768


class RecordingVectorRepository:
    def __init__(self):
        self.calls = []

    def search_chunks(self, **kwargs):
        self.calls.append(kwargs)
        return []


def _context(role: str = "customer", user_id: str = "11111111-1111-1111-1111-111111111111"):
    return RequestContext(
        session_id="test-session",
        user=AuthenticatedUser(
            user_id=user_id,
            email=f"{role}@example.local",
            name=role,
            role=role,
        ),
    )


def test_roles_and_tool_level_authorization():
    anonymous = RequestContext(session_id="anon")
    customer = _context("customer")
    support_agent = _context("support_agent")

    assert authorize_tool("search_products", anonymous).allowed is True
    assert authorize_tool("check_order_status", anonymous).allowed is False
    assert authorize_tool("cancel_customer_order", anonymous).allowed is False
    assert authorize_tool("check_order_status", customer).allowed is True
    assert authorize_tool("check_order_status", support_agent).allowed is True


def test_workflow_level_authorization():
    anonymous = RequestContext(session_id="anon")
    customer = _context("customer")

    assert authorize_workflow("product_search", anonymous).allowed is True
    assert authorize_workflow("rag_policy", anonymous).allowed is True
    assert authorize_workflow("order_status", anonymous).allowed is False
    assert authorize_workflow("order_status", customer).allowed is True


def test_resource_ownership_filter_by_role():
    anonymous = RequestContext(session_id="anon")
    customer = _context("customer", "22222222-2222-2222-2222-222222222222")
    manager = _context("manager", "33333333-3333-3333-3333-333333333333")

    assert order_owner_filter_user_id(anonymous) == "__unauthorized__"
    assert order_owner_filter_user_id(customer) == "22222222-2222-2222-2222-222222222222"
    assert order_owner_filter_user_id(manager) is None


def test_knowledge_level_authorization_scope_uses_role_access():
    repository = RecordingVectorRepository()
    service = KnowledgeService(
        embedding_provider=StaticEmbeddingProvider(),
        vector_repository=repository,
    )

    with request_context(_context("support_agent")):
        assert knowledge_access_level(get_request_context()) == "internal"
        service._search_postgres_rag("internal policy")

    assert repository.calls[0]["role"] == Role.SUPPORT_AGENT.value
    assert repository.calls[0]["department"] == "support"
    assert repository.calls[0]["access_level"] == "internal"


if __name__ == "__main__":
    test_roles_and_tool_level_authorization()
    test_workflow_level_authorization()
    test_resource_ownership_filter_by_role()
    test_knowledge_level_authorization_scope_uses_role_access()
    print("RBAC authorization tests passed.")
