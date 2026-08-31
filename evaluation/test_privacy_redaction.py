import sys
from pathlib import Path

from langchain_core.messages import HumanMessage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthenticatedUser, RequestContext, request_context  # noqa: E402
from core.privacy import detect_pii, redact_for_logs, redact_text  # noqa: E402
from core.privacy.pii import redact_message_content  # noqa: E402
from core.services.order_service import OrderService  # noqa: E402


class FakeOrderRepository:
    def find_order_with_product(self, order_id, user_id=None):
        return {
            "id": order_id,
            "customer_name": "Budi Santoso",
            "product_name": "Nike Air Max Shoes",
            "quantity": 1,
            "total_price": 1200000,
            "status": "Processing",
            "shipping_address": "Jl. Melati No. 7, Jakarta",
            "order_date": "2026-08-01",
            "estimated_arrival": None,
        }

    def find_order_for_update(self, order_id, user_id=None):
        return {
            "id": order_id,
            "status": "Processing",
            "customer_name": "Budi Santoso",
            "shipping_address": "Jl. Melati No. 7, Jakarta",
        }

    def update_order_shipping_address(self, order_id, new_address, user_id=None):
        self.updated_address = new_address


def test_redact_text_removes_known_pii():
    source = (
        "Customer: Budi Santoso, email budi@example.com, phone +6281234567890, "
        "customer_id=11111111-1111-1111-1111-111111111111, "
        "Address: Jl. Melati No. 7, Jakarta, payment_reference=PAY-123"
    )
    redacted = redact_text(source)

    assert "Budi Santoso" not in redacted
    assert "budi@example.com" not in redacted
    assert "+6281234567890" not in redacted
    assert "11111111-1111-1111-1111-111111111111" not in redacted
    assert "Jl. Melati" not in redacted
    assert "PAY-123" not in redacted
    assert detect_pii(redacted) == {}


def test_redact_message_content_for_external_llm_payloads():
    message = HumanMessage(content="Please ship to Jl. Mawar No. 9, Bandung for Siti Aminah")
    redacted = redact_message_content(message)

    assert redacted is not message
    assert "Jl. Mawar" not in redacted.content
    assert "Siti Aminah" not in redacted.content
    assert detect_pii(redacted.content) == {}


def test_order_service_minimizes_pii_in_customer_responses():
    user = AuthenticatedUser(
        user_id="11111111-1111-1111-1111-111111111111",
        email="budi@example.local",
        name="Budi Santoso",
        role="customer",
    )
    service = OrderService(repository=FakeOrderRepository())

    with request_context(RequestContext(session_id="privacy-test", user=user)):
        status_response = service.check_order_status("ORD001")
        update_response = service.update_order_address("ORD001", "Jl. Baru No. 10, Jakarta")

    assert "Budi Santoso" not in status_response
    assert "Jl. Melati" not in status_response
    assert "saved on order" in status_response
    assert "Jl. Baru" not in update_response
    assert "currently disabled" in update_response


def test_redact_for_logs_handles_nested_structures():
    source = {
        "args": {"new_address": "Jl. Sudirman No. 100, Jakarta"},
        "output": "Customer: Doni Pratama\nAddress: Jl. Sudirman No. 100, Jakarta",
    }
    redacted = redact_for_logs(source)

    assert detect_pii(redacted) == {}


if __name__ == "__main__":
    test_redact_text_removes_known_pii()
    test_redact_message_content_for_external_llm_payloads()
    test_order_service_minimizes_pii_in_customer_responses()
    test_redact_for_logs_handles_nested_structures()
    print("Privacy redaction tests passed.")
