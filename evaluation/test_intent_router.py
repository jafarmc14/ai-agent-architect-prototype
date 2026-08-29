from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workflows import Intent, classify_intent, route_intent  # noqa: E402


def test_intent_taxonomy_classification():
    cases = {
        "Find comfortable shoes under Rp 1,500,000": Intent.PRODUCT_SEARCH,
        "Do you have Nike shoes in stock?": Intent.PRODUCT_INFO,
        "Compare Nike and Adidas shoes": Intent.PRODUCT_COMPARE,
        "Track my order ORD001": Intent.ORDER_STATUS,
        "What is your refund policy?": Intent.RETURN_POLICY,
        "Add 2 Nike shoes to my cart": Intent.CART,
        "Cancel order ORD002": Intent.TRANSACTION,
        "My order arrived damaged and I am frustrated": Intent.COMPLAINT,
        "I want to speak to a human agent": Intent.ESCALATION,
        "What are your store operating hours?": Intent.GENERAL_FAQ,
        "What is quantum gravity?": Intent.UNKNOWN,
    }

    for query, expected_intent in cases.items():
        assert classify_intent(query) == expected_intent


def test_router_bypasses_agent_loop_for_simple_workflows():
    assert route_intent("How long does international shipping take?").workflow == "rag_policy"
    assert route_intent("How long does international shipping take?").use_agent_loop is False

    assert route_intent("Track my order ORD001").workflow == "order_status"
    assert route_intent("Track my order ORD001").use_agent_loop is False

    assert route_intent("Show me all electronics products").workflow == "product_search"
    assert route_intent("Show me all electronics products").use_agent_loop is False


def test_router_keeps_complex_and_write_requests_in_agent_loop():
    assert route_intent("My order arrived damaged and I want a replacement").use_agent_loop is True
    assert route_intent("Cancel my order ORD002").use_agent_loop is True
    assert route_intent("Add 2 Nike shoes to my cart").use_agent_loop is True
    assert route_intent("Hello, what can you help me with?").use_agent_loop is True


if __name__ == "__main__":
    test_intent_taxonomy_classification()
    test_router_bypasses_agent_loop_for_simple_workflows()
    test_router_keeps_complex_and_write_requests_in_agent_loop()
    print("Intent router tests passed.")
