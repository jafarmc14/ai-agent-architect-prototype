import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthenticatedUser, RequestContext, request_context  # noqa: E402
from core.services.support_service import SupportService  # noqa: E402
from core.workflows.escalation_rules import evaluate_escalation  # noqa: E402


class CapturingSupportRepository:
    def __init__(self):
        self.payloads = []

    def insert_support_ticket(self, *args, **kwargs):
        self.payloads.append({"args": args, "kwargs": kwargs})
        return "TICKET-TEST"


def test_automatic_escalation_rules_assign_priority():
    cases = [
        ("This looks like fraud on my account", "Urgent", "fraud"),
        ("I will file a legal complaint about this order", "Urgent", "legal_complaint"),
        ("I was charged twice, this is a payment dispute", "High", "payment_dispute"),
        ("I need a refund Rp5000000 for this failed order", "High", "high_value_refund"),
        ("This failed for the third time", "High", "repeated_failure"),
        ("I want to speak to human agent", "Normal", "human_requested"),
    ]

    for message, priority, escalation_type in cases:
        decision = evaluate_escalation(message)
        assert decision.should_escalate is True
        assert decision.priority == priority
        assert decision.escalation_type == escalation_type
        assert decision.summarized_context


def test_low_confidence_triggers_escalation():
    decision = evaluate_escalation("ambiguous unresolved request", confidence=0.2)

    assert decision.should_escalate is True
    assert decision.priority == "Normal"
    assert "low_confidence" in decision.matched_rules


def test_support_ticket_includes_priority_and_summarized_context():
    repository = CapturingSupportRepository()
    service = SupportService(repository=repository)
    user = AuthenticatedUser(
        user_id="11111111-1111-1111-1111-111111111111",
        role="customer",
        tenant_id="default",
    )

    with request_context(RequestContext(session_id="support-test", user=user)):
        response = service.create_support_ticket("This looks like fraud on my account")

    assert "TICKET-TEST" in response
    assert "Priority: Urgent" in response
    payload = repository.payloads[0]["kwargs"]
    assert payload["escalation_type"] == "fraud"
    assert payload["escalation_reason"] == "fraud"
    assert "Customer message summary" in payload["summarized_context"]
    assert payload["metadata"]["matched_rules"] == ["fraud"]


if __name__ == "__main__":
    test_automatic_escalation_rules_assign_priority()
    test_low_confidence_triggers_escalation()
    test_support_ticket_includes_priority_and_summarized_context()
    print("Human escalation tests passed.")
