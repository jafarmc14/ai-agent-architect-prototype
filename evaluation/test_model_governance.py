from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.base import LLMResponse  # noqa: E402
from core.llm.gateway import LLMGateway  # noqa: E402
from core.llm.model_governance import build_model_governance  # noqa: E402


class FakeProvider:
    provider_name = "fake"
    model = "fake-alias"
    model_version = "alias:fake-alias"
    model_governance = build_model_governance("fake", "fake-alias")
    client = None

    def generate_sync(self, messages, tools=None, temperature=None, **kwargs):
        return LLMResponse(
            text="ok",
            usage={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            model=self.model,
            model_version=self.model_version,
            model_metadata=self.model_governance.metadata(),
        )


class CapturingLLMRequestRepository:
    def __init__(self):
        self.requests = []

    def insert_request(self, **kwargs):
        self.requests.append(kwargs)


def test_openrouter_free_is_observed_as_unpinned_alias():
    governance = build_model_governance("openrouter", "openrouter/free")

    assert governance.provider == "openrouter"
    assert governance.model == "openrouter/free"
    assert governance.model_version == "alias:openrouter/free"
    assert governance.pinned is False
    assert governance.alias is True


def test_ollama_tag_without_digest_is_observed_as_unpinned_alias():
    governance = build_model_governance("ollama", "llama3.1")

    assert governance.model_version == "alias:llama3.1"
    assert governance.pinned is False
    assert governance.alias is True


def test_configured_model_version_is_pinned():
    governance = build_model_governance("openrouter", "meta-llama/llama-3.1-8b-instruct", "2026-08-31")

    assert governance.model_version == "2026-08-31"
    assert governance.pinned is True
    assert governance.alias is False


def test_gateway_logs_provider_model_and_model_version():
    gateway = LLMGateway(provider=FakeProvider())
    repository = CapturingLLMRequestRepository()
    gateway.request_repository = repository

    response = gateway.generate_sync([{"role": "user", "content": "hello"}])

    assert response.text == "ok"
    assert repository.requests
    request = repository.requests[0]
    assert request["provider"] == "fake"
    assert request["model"] == "fake-alias"
    assert request["model_version"] == "alias:fake-alias"
    assert request["model_metadata"]["pinned"] is False


if __name__ == "__main__":
    test_openrouter_free_is_observed_as_unpinned_alias()
    test_ollama_tag_without_digest_is_observed_as_unpinned_alias()
    test_configured_model_version_is_pinned()
    test_gateway_logs_provider_model_and_model_version()
    print("Model governance tests passed.")
