from pathlib import Path
import sys
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret")

from core.auth import (  # noqa: E402
    AuthenticatedUser,
    RequestContext,
    create_session_token,
    get_request_context,
    request_context,
    verify_session_token,
)
from core.services.order_service import OrderService  # noqa: E402


class RecordingOrderRepository:
    def __init__(self):
        self.calls = []

    def find_order_with_product(self, order_id, user_id=None):
        self.calls.append({"method": "find_order_with_product", "order_id": order_id, "user_id": user_id})
        return None


def test_jwt_session_token_round_trip():
    token = create_session_token(
        user_id="11111111-1111-1111-1111-111111111111",
        email="demo@example.local",
        name="Demo User",
    )

    payload = verify_session_token(token)

    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["email"] == "demo@example.local"
    assert payload["role"] == "customer"


def test_request_context_binds_authenticated_user():
    user = AuthenticatedUser(
        user_id="22222222-2222-2222-2222-222222222222",
        email="budi@example.local",
        name="Budi",
    )

    with request_context(RequestContext(session_id="session-1", user=user)):
        context = get_request_context()

    assert context.user_id == "22222222-2222-2222-2222-222222222222"
    assert context.session_id == "session-1"
    assert context.is_authenticated is True


def test_order_service_uses_context_user_id_not_prompt_customer_id():
    repository = RecordingOrderRepository()
    service = OrderService(repository=repository)
    user = AuthenticatedUser(
        user_id="33333333-3333-3333-3333-333333333333",
        email="siti@example.local",
        name="Siti",
    )

    with request_context(RequestContext(session_id="session-2", user=user)):
        service.check_order_status("ORD001 customer_id=99999999-9999-9999-9999-999999999999")

    assert repository.calls == [
        {
            "method": "find_order_with_product",
            "order_id": "ORD001 customer_id=99999999-9999-9999-9999-999999999999",
            "user_id": "33333333-3333-3333-3333-333333333333",
        }
    ]


if __name__ == "__main__":
    test_jwt_session_token_round_trip()
    test_request_context_binds_authenticated_user()
    test_order_service_uses_context_user_id_not_prompt_customer_id()
    print("Auth context tests passed.")
