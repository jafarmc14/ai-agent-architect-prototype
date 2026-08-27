from core.repositories import SupportRepository


class SupportService:
    """Business logic for human escalation and support tickets."""

    def __init__(self, repository: SupportRepository | None = None):
        self.repository = repository or SupportRepository()

    def create_support_ticket(self, customer_message: str, agent_summary: str = "", priority: str = "Normal") -> str:
        ticket_id = self.repository.insert_support_ticket(customer_message, agent_summary, priority)
        return f"🎫 Support ticket #{ticket_id} created successfully (Priority: {priority}). A human agent will review your case within 1x24 hours."


support_service = SupportService()
