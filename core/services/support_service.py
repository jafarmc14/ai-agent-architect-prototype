from core.auth import get_request_context
from core.repositories import SupportRepository
from core.workflows.escalation_rules import evaluate_escalation, summarize_escalation_context


VALID_PRIORITIES = {"Low", "Normal", "High", "Urgent"}


class SupportService:
    """Business logic for human escalation and support tickets."""

    def __init__(self, repository: SupportRepository | None = None):
        self.repository = repository or SupportRepository()

    def create_support_ticket(
        self,
        customer_message: str,
        agent_summary: str = "",
        priority: str = "Normal",
        escalation_type: str = "",
        escalation_reason: str = "",
        summarized_context: str = "",
    ) -> str:
        context = get_request_context()
        normalized_priority = _normalize_priority(priority)
        decision = evaluate_escalation(customer_message)
        if decision.should_escalate:
            normalized_priority = _max_priority(normalized_priority, decision.priority)
            escalation_type = escalation_type or decision.escalation_type
            escalation_reason = escalation_reason or decision.reason
            summarized_context = summarized_context or decision.summarized_context

        summarized_context = summarized_context or summarize_escalation_context(customer_message)
        agent_summary = agent_summary or summarized_context
        ticket_id = self.repository.insert_support_ticket(
            customer_message,
            agent_summary,
            normalized_priority,
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            escalation_type=escalation_type,
            escalation_reason=escalation_reason,
            summarized_context=summarized_context,
            metadata={
                "matched_rules": list(decision.matched_rules),
                "confidence": decision.confidence,
            },
        )
        return (
            f"Support ticket #{ticket_id} created successfully "
            f"(Priority: {normalized_priority}, Type: {escalation_type or 'manual'}). "
            "A human agent will review your case within 1x24 hours."
        )


def _normalize_priority(priority: str) -> str:
    lowered = str(priority or "Normal").strip().lower()
    for candidate in VALID_PRIORITIES:
        if candidate.lower() == lowered:
            return candidate
    return "Normal"


def _max_priority(left: str, right: str) -> str:
    order = {"Low": 1, "Normal": 2, "High": 3, "Urgent": 4}
    return left if order[left] >= order[right] else right


support_service = SupportService()
