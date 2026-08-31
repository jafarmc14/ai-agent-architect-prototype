from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from core.auth import RequestContext, request_context  # noqa: E402
from core.services.conversation_service import ConversationService  # noqa: E402


class FakeConversationRepository:
    def __init__(self):
        self.conversations = {}
        self.messages = {}

    def get_or_create_conversation(self, *, session_id, user_id=None, tenant_id="default", channel="streamlit"):
        conversation_id = f"{tenant_id}:{user_id or session_id}"
        self.conversations.setdefault(
            conversation_id,
            {
                "id": conversation_id,
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "channel": channel,
                "structured_state": {},
            },
        )
        return dict(self.conversations[conversation_id])

    def append_message(
        self,
        *,
        conversation_id,
        role,
        content,
        tenant_id="default",
        metadata=None,
        tool_name="",
        tool_arguments=None,
        tool_output=None,
    ):
        self.messages.setdefault(conversation_id, []).append(
            {
                "role": role,
                "content": content,
                "tenant_id": tenant_id,
                "metadata": metadata or {},
                "tool_name": tool_name,
                "tool_arguments": tool_arguments or {},
                "tool_output": tool_output or {},
            }
        )

    def recent_messages(self, *, conversation_id, limit=6):
        return list(self.messages.get(conversation_id, []))[-limit:]

    def get_structured_state(self, *, conversation_id):
        return dict(self.conversations.get(conversation_id, {}).get("structured_state", {}))

    def update_structured_state(self, *, conversation_id, structured_state):
        self.conversations.setdefault(conversation_id, {})["structured_state"] = structured_state

    def reset_memory(self):
        self.conversations.clear()
        self.messages.clear()


def test_transcript_and_structured_state_are_separate():
    repository = FakeConversationRepository()
    service = ConversationService(repository=repository)

    with request_context(RequestContext(session_id="phase19-test", tenant_id="tenant-a")):
        service.record_turn(
            "Find black shoes under Rp500,000",
            "No matching products found.",
            {"workflow": "product_search", "tool_calls": [{"name": "search_products", "args": {"query": "black shoes"}}]},
        )

    conversation_id = "tenant-a:phase19-test"
    messages = repository.messages[conversation_id]
    state = repository.conversations[conversation_id]["structured_state"]

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert "Find black shoes" in messages[0]["content"]
    assert state["last_intent"] == "PRODUCT_SEARCH"
    assert state["last_product_filters"]["catalog_category"] == "Shoes"
    assert state["last_product_filters"]["color"] == "black"
    assert state["last_product_filters"]["max_price"] == 500000


def test_product_constraints_are_retained_across_turns():
    repository = FakeConversationRepository()
    service = ConversationService(repository=repository)

    with request_context(RequestContext(session_id="phase19-constraints", tenant_id="tenant-a")):
        service.update_structured_state("Find black shoes under Rp500,000")
        state = service.update_structured_state("Only available ones please")

    filters = state["last_product_filters"]
    assert filters["catalog_category"] == "Shoes"
    assert filters["color"] == "black"
    assert filters["max_price"] == 500000
    assert filters["available"] is True
    assert filters["hard_constraints"]["max_price"] == 500000
    assert filters["hard_constraints"]["availability"] is True


def test_recent_messages_for_llm_does_not_depend_on_full_history():
    repository = FakeConversationRepository()
    service = ConversationService(repository=repository)

    with request_context(RequestContext(session_id="phase19-history", tenant_id="tenant-a")):
        conversation = service.get_or_create_current_conversation()
        conversation_id = str(conversation["id"])
        for index in range(10):
            repository.append_message(conversation_id=conversation_id, role="user", content=f"user {index}")
            repository.append_message(conversation_id=conversation_id, role="assistant", content=f"assistant {index}")

        messages = service.recent_messages_for_llm(limit=6)

    assert len(messages) == 6
    assert isinstance(messages[0], HumanMessage)
    assert isinstance(messages[1], AIMessage)
    assert messages[0].content == "user 7"
    assert messages[-1].content == "assistant 9"


if __name__ == "__main__":
    test_transcript_and_structured_state_are_separate()
    test_product_constraints_are_retained_across_turns()
    test_recent_messages_for_llm_does_not_depend_on_full_history()
    print("Conversation state tests passed.")
