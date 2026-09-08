import importlib
import re
import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.orchestration.runtime as runtime  # noqa: E402
from core.auth import RequestContext, request_context  # noqa: E402
from core.services.cart_service import CartService  # noqa: E402
from core.services.order_service import OrderService  # noqa: E402
from core.services.write_action_service import WriteActionService  # noqa: E402

cart_service_module = importlib.import_module("core.services.cart_service")


class FakeProductRepository:
    def find_products_by_name(self, product_name):
        return [
            {
                "id": "product-1",
                "name": "Nike Air Max Shoes",
                "category": "Shoes",
                "price": 1_200_000,
                "stock": 50,
                "country": "Indonesia",
            }
        ]


class FakeCartRepository:
    def __init__(self):
        self.quantity = 0
        self.inserts = 0
        self.updates = 0

    def find_cart_item(self, session_id, product_id, user_id=None):
        if self.quantity <= 0:
            return None
        return {"id": "cart-item-1", "quantity": self.quantity}

    def update_cart_quantity(self, cart_item_id, quantity):
        self.quantity = quantity
        self.updates += 1

    def insert_cart_item(self, session_id, product_id, quantity, user_id=None):
        self.quantity = quantity
        self.inserts += 1

    def list_cart_items(self, session_id, user_id=None):
        if self.quantity <= 0:
            return []
        return [{"name": "Nike Air Max Shoes", "quantity": self.quantity, "subtotal": self.quantity * 1_200_000}]

    def delete_cart_items(self, session_id, user_id=None):
        deleted = 1 if self.quantity else 0
        self.quantity = 0
        return deleted


class FakeOrderRepository:
    def __init__(self):
        self.cancel_calls = 0

    def find_order_for_update(self, order_id, user_id=None):
        return {"id": order_id, "status": "Processing", "shipping_address": "Old address"}

    def update_order_status(self, order_id, status, user_id=None):
        self.cancel_calls += 1


class CapturingWriteControlRepository:
    def __init__(self):
        self.idempotency_records = {}
        self.audit_logs = []

    def find_idempotency_record(self, idempotency_key, tenant_id="default"):
        return self.idempotency_records.get((tenant_id, idempotency_key))

    def record_idempotency(self, **kwargs):
        self.idempotency_records[(kwargs["tenant_id"], kwargs["idempotency_key"])] = kwargs

    def insert_audit_log(self, **kwargs):
        self.audit_logs.append(kwargs)


def test_cart_add_requires_confirmation_then_executes_once():
    cart_repo = FakeCartRepository()
    service = CartService(cart_repository=cart_repo, product_repository=FakeProductRepository())
    original_write_action_service = cart_service_module.write_action_service
    isolated_write_action_service = WriteActionService(repository=CapturingWriteControlRepository())
    cart_service_module.write_action_service = isolated_write_action_service

    try:
        with request_context(RequestContext(session_id="controlled-write-cart-isolated")):
            first_response = service.add_to_cart("Nike shoes", 2)
            assert "Confirmation required" in first_response
            assert cart_repo.quantity == 0

            confirmation_id = re.search(r"confirm ([a-f0-9]{8})", first_response).group(1)
            pending = isolated_write_action_service.consume_confirmation(f"confirm {confirmation_id}")
            assert pending is not None

            confirmed_response = service.add_to_cart(
                pending.payload["product_name"],
                pending.payload["quantity"],
                confirmed=True,
                idempotency_key=pending.idempotency_key,
                request_id=pending.request_id,
            )
            assert "Added to cart" in confirmed_response
            assert cart_repo.quantity == 2

            retry_response = service.add_to_cart(
                pending.payload["product_name"],
                pending.payload["quantity"],
                confirmed=True,
                idempotency_key=pending.idempotency_key,
                request_id=pending.request_id,
            )
            assert retry_response == confirmed_response
            assert cart_repo.quantity == 2
    finally:
        cart_service_module.write_action_service = original_write_action_service


def test_high_risk_order_cancellation_is_disabled_initially():
    repo = FakeOrderRepository()
    service = OrderService(repository=repo)

    with request_context(RequestContext(session_id="controlled-write-order")):
        response = service.cancel_order("ORD001")

    assert "currently disabled" in response
    assert repo.cancel_calls == 0


def test_audit_log_captures_who_what_when_resource_and_values():
    repository = CapturingWriteControlRepository()
    service = WriteActionService(repository=repository)

    with request_context(RequestContext(session_id="audit-session")):
        service.record_success(
            action="cart.add_item",
            resource_type="product",
            resource_id="product-1",
            old_value={"quantity": 0},
            new_value={"quantity": 2},
            response="Added to cart",
            idempotency_key="idem-1",
            request_id="request-1",
        )

    assert repository.audit_logs
    audit = repository.audit_logs[0]
    assert audit["action"] == "cart.add_item"
    assert audit["resource_type"] == "product"
    assert audit["resource_id"] == "product-1"
    assert audit["old_value"] == {"quantity": 0}
    assert audit["new_value"] == {"quantity": 2}
    assert audit["request_id"] == "request-1"
    assert audit["idempotency_key"] == "idem-1"


def test_disabled_high_risk_write_returns_deterministic_message():
    original_get_settings = runtime.get_settings
    runtime.get_settings = lambda: SimpleNamespace(high_risk_write_actions_enabled=False)
    try:
        assert "disabled" in runtime._disabled_write_response("I want to cancel my order ORD002")
        assert "disabled" in runtime._disabled_write_response("Change the address for ORD005 to Jl. Sudirman No. 100")
        assert "disabled" in runtime._disabled_write_response("Please update shipping address for ORD001")
        assert runtime._disabled_write_response("What is the status of order ORD001?") is None
        assert runtime._disabled_write_response("Find shoes under Rp 1,500,000") is None
    finally:
        runtime.get_settings = original_get_settings


def test_disabled_high_risk_write_allows_requests_when_enabled():
    original_get_settings = runtime.get_settings
    runtime.get_settings = lambda: SimpleNamespace(high_risk_write_actions_enabled=True)
    try:
        assert runtime._disabled_write_response("I want to cancel my order ORD002") is None
        assert runtime._disabled_write_response("Change the address for ORD005") is None
    finally:
        runtime.get_settings = original_get_settings


if __name__ == "__main__":
    test_cart_add_requires_confirmation_then_executes_once()
    test_high_risk_order_cancellation_is_disabled_initially()
    test_audit_log_captures_who_what_when_resource_and_values()
    test_disabled_high_risk_write_returns_deterministic_message()
    test_disabled_high_risk_write_allows_requests_when_enabled()
    print("Controlled write action tests passed.")
