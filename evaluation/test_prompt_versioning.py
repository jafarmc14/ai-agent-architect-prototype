from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.base import LLMResponse  # noqa: E402
from core.llm.gateway import LLMGateway  # noqa: E402
from core.prompts import PromptRegistry, get_system_prompt_metadata, prompt_registry, rollback_prompt_version  # noqa: E402


class FakeProvider:
    provider_name = "fake"
    model = "fake-model"
    client = None

    def generate_sync(self, messages, tools=None, temperature=None, **kwargs):
        return LLMResponse(text="ok", tool_calls=[], usage={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3})

    def generate_structured_sync(self, messages, schema, temperature=None, **kwargs):
        return {"ok": True}


class CapturingLLMRequestRepository:
    def __init__(self):
        self.requests = []

    def insert_request(self, **kwargs):
        self.requests.append(kwargs)


def test_prompt_registry_tracks_active_metadata_and_rollback():
    active = prompt_registry.active("system")
    metadata = active.metadata()

    assert metadata["prompt_id"] == "system"
    assert metadata["version"] == "v2"
    assert metadata["prompt_key"] == "system_v2"
    assert metadata["status"] == "active"

    rolled_back = prompt_registry.rollback("system", "v1")
    assert rolled_back.active("system").version == "v1"
    assert rolled_back.active("system").status == "active"


def test_runtime_prompt_metadata_accessor():
    metadata = get_system_prompt_metadata()

    assert metadata["prompt_id"] == "system"
    assert metadata["version"]
    assert metadata["prompt_key"] == f"{metadata['prompt_id']}_{metadata['version']}"


def test_global_prompt_rollback_support():
    current = get_system_prompt_metadata()["version"]
    rolled_back = rollback_prompt_version("system", "v1")
    assert rolled_back["version"] == "v1"
    rollback_prompt_version("system", current)
    assert get_system_prompt_metadata()["version"] == current


def test_llm_gateway_logs_prompt_version_on_request():
    gateway = LLMGateway(provider=FakeProvider())
    repository = CapturingLLMRequestRepository()
    gateway.request_repository = repository

    response = gateway.generate_sync([{"role": "user", "content": "hello"}])

    assert response.text == "ok"
    assert repository.requests
    prompt_metadata = repository.requests[0]["prompt_metadata"]
    assert prompt_metadata["prompt_id"] == "system"
    assert prompt_metadata["version"]
    assert prompt_metadata["prompt_key"]


def test_identity_and_prompt_version_questions_do_not_use_tools_or_escalate():
    import agent

    for query in ("Who are you?", "What prompt version are you using?"):
        result = agent.get_agent_response_with_trace(query, session_id="prompt-version-direct-regression")
        assert result["exception"] is None
        assert result["tool_calls"] == []
        assert result["workflow"] in {"identity", "internal_metadata_refusal"}
        assert "Support ticket" not in result["response"]
        assert result.get("prompt", {}).get("prompt_key") == "system_v2"


if __name__ == "__main__":
    test_prompt_registry_tracks_active_metadata_and_rollback()
    test_runtime_prompt_metadata_accessor()
    test_global_prompt_rollback_support()
    test_llm_gateway_logs_prompt_version_on_request()
    test_identity_and_prompt_version_questions_do_not_use_tools_or_escalate()
    print("Prompt versioning tests passed.")
