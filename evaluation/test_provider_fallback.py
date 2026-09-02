import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.base import LLMResponse  # noqa: E402
from core.llm.gateway import LLMGateway  # noqa: E402
from core.llm.provider_fallback import (  # noqa: E402
    InvalidProviderResponse,
    ProviderFallbackPolicy,
)
import core.orchestration.runtime as runtime  # noqa: E402


class HTTPFailure(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP error {status_code}")
        self.status_code = status_code


class ScriptedProvider:
    model_version = "test-v1"
    supports_prompt_caching = False
    client = None

    def __init__(self, provider_name: str, model: str, outcomes=None):
        self.provider_name = provider_name
        self.model = model
        self.outcomes = list(outcomes or [LLMResponse(text="fallback success")])
        self.calls = 0

    def _next(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def generate_sync(self, messages, tools=None, temperature=None, **kwargs):
        return self._next()

    async def generate(self, messages, tools=None, temperature=None, **kwargs):
        return self._next()

    def generate_structured_sync(self, messages, schema, temperature=None, **kwargs):
        return self._next()

    async def generate_structured(self, messages, schema, temperature=None, **kwargs):
        return self._next()


class CapturingRepository:
    def __init__(self):
        self.requests = []

    def insert_request(self, **payload):
        self.requests.append(payload)


def test_failure_classification_covers_required_transient_failures():
    policy = ProviderFallbackPolicy(_settings())
    cases = [
        (HTTPFailure(429), "rate_limit"),
        (HTTPFailure(500), "provider_server_error"),
        (TimeoutError("timed out"), "timeout"),
        (InvalidProviderResponse("empty"), "invalid_response"),
        (ConnectionError("connection refused"), "connection_failure"),
    ]
    for error, expected in cases:
        classification = policy.classify(error)
        assert classification.category == expected
        assert classification.retryable is True


def test_sync_gateway_recovers_all_required_failure_types():
    failures = [
        HTTPFailure(429),
        HTTPFailure(500),
        TimeoutError("timed out"),
        LLMResponse(text=""),
        ConnectionError("connection refused"),
    ]
    expected_categories = [
        "rate_limit", "provider_server_error", "timeout", "invalid_response", "connection_failure",
    ]
    for failure, category in zip(failures, expected_categories):
        gateway, primary, fallback, repository = _gateway(failure)
        response = gateway.generate_sync([{"role": "user", "content": "test"}], task="orders")

        assert response.text == "fallback success"
        assert primary.calls == 1
        assert fallback.calls == 1
        assert repository.requests[0]["metadata"]["fallback"]["attempt"]["failure"]["category"] == category
        final = repository.requests[-1]
        assert final["provider"] == "deepseek"
        assert final["metadata"]["fallback"]["fallback_used"] is True


def test_async_and_structured_paths_use_the_same_fallback_policy():
    gateway, _, _, repository = _gateway(TimeoutError("timed out"))
    response = asyncio.run(gateway.generate([{"role": "user", "content": "test"}], task="orders"))
    assert response.text == "fallback success"
    assert repository.requests[-1]["provider"] == "deepseek"

    gateway, _, fallback, repository = _gateway(None, structured=True)
    result = gateway.generate_structured_sync(
        [{"role": "user", "content": "extract"}], schema={"type": "object"}, task="extraction",
    )
    assert result == {"intent": "ORDER_STATUS"}
    assert fallback.calls == 1
    assert repository.requests[-1]["metadata"]["fallback"]["fallback_used"] is True


def test_non_retryable_errors_do_not_switch_provider():
    gateway, primary, fallback, repository = _gateway(HTTPFailure(401))
    try:
        gateway.generate_sync([{"role": "user", "content": "test"}], task="orders")
        raise AssertionError("Expected authentication failure")
    except HTTPFailure as exc:
        assert exc.status_code == 401
    assert primary.calls == 1
    assert fallback.calls == 0
    assert len(repository.requests) == 1
    assert repository.requests[0]["metadata"]["fallback"]["will_retry"] is False


def test_external_fallback_keeps_privacy_redaction_active_for_local_primary():
    original_gateway = runtime.llm_gateway
    original_get_settings = runtime.get_settings
    runtime.llm_gateway = SimpleNamespace(provider_name="ollama")
    runtime.get_settings = lambda: SimpleNamespace(
        model_routing_enabled=False,
        provider_fallback_enabled=True,
        provider_fallback_chain="deepseek,ollama",
        openrouter_api_key="",
        deepseek_api_key="configured",
        kimi_api_key="",
    )
    try:
        assert runtime._is_external_llm_provider() is True
    finally:
        runtime.llm_gateway = original_gateway
        runtime.get_settings = original_get_settings


def _gateway(failure, *, structured=False):
    primary_outcome = None if structured else failure
    if structured:
        primary_outcome = ""
        fallback_outcome = {"intent": "ORDER_STATUS"}
    else:
        primary_outcome = failure if failure is not None else LLMResponse(text="")
        fallback_outcome = LLMResponse(text="fallback success")
    primary = ScriptedProvider("openrouter", "openrouter/free", [primary_outcome])
    fallback = ScriptedProvider("deepseek", "deepseek-v4-flash", [fallback_outcome])
    gateway = LLMGateway(provider=primary)
    gateway.fallback_policy = ProviderFallbackPolicy(_settings())
    gateway._provider_cache = {
        (primary.provider_name, primary.model): primary,
        (fallback.provider_name, fallback.model): fallback,
    }
    gateway._build_provider = lambda provider_name=None, model=None: ScriptedProvider(provider_name, model)
    repository = CapturingRepository()
    gateway.request_repository = repository
    return gateway, primary, fallback, repository


def _settings():
    return SimpleNamespace(
        provider_fallback_enabled=True,
        provider_fallback_chain="deepseek,kimi,openrouter,ollama",
        provider_fallback_max_attempts=3,
        provider_fallback_backoff_seconds=0.0,
        openrouter_api_key="configured",
        openrouter_model="openrouter/free",
        ollama_model="llama3.1",
        deepseek_api_key="configured",
        deepseek_model="deepseek-v4-flash",
        kimi_api_key="configured",
        kimi_model="kimi-k2.6",
    )


if __name__ == "__main__":
    test_failure_classification_covers_required_transient_failures()
    test_sync_gateway_recovers_all_required_failure_types()
    test_async_and_structured_paths_use_the_same_fallback_policy()
    test_non_retryable_errors_do_not_switch_provider()
    test_external_fallback_keeps_privacy_redaction_active_for_local_primary()
    print("Provider fallback pipeline tests passed.")
