from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.base import LLMResponse  # noqa: E402
from core.llm.gateway import LLMGateway  # noqa: E402
from core.llm.model_routing import ModelRouter  # noqa: E402


class FakeProvider:
    model_version = "test-v1"
    supports_prompt_caching = False
    client = None

    def __init__(self, provider_name: str, model: str):
        self.provider_name = provider_name
        self.model = model

    def generate_sync(self, messages, tools=None, temperature=None, **kwargs):
        return LLMResponse(
            text=f"response from {self.provider_name}",
            usage={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            model=self.model,
            model_version=self.model_version,
        )


class CapturingRepository:
    def __init__(self):
        self.requests = []

    def insert_request(self, **payload):
        self.requests.append(payload)


def test_routing_disabled_preserves_configured_provider():
    router = ModelRouter(_settings(enabled=False))
    decision = _decide(router, task="agentic_workflow", complexity="high", evidence_score=1.0)
    assert decision.provider == "openrouter"
    assert decision.model == "openrouter/free"
    assert decision.enabled is False
    assert decision.premium_model_used is False


def test_routes_by_task_and_complexity_with_cheap_first():
    router = ModelRouter(_settings())
    cheap = _decide(router, task="orders", complexity="low", confidence=0.95, evidence_score=1.0)
    standard = _decide(router, task="simple_rag", complexity="medium", confidence=0.95, evidence_score=1.0)
    premium = _decide(router, task="agentic_workflow", complexity="high", confidence=0.95, evidence_score=1.0)

    assert (cheap.selected_tier, cheap.provider) == ("cheap", "openrouter")
    assert cheap.cheap_first is True
    assert (standard.selected_tier, standard.provider) == ("standard", "deepseek")
    assert (premium.selected_tier, premium.provider) == ("premium", "kimi")
    assert premium.premium_model_used is True


def test_confidence_and_evidence_quality_control_escalation():
    router = ModelRouter(_settings())
    low_confidence = _decide(
        router, task="simple_rag", complexity="medium", confidence=0.2, evidence_score=0.9,
    )
    missing_evidence = _decide(
        router, task="agentic_workflow", complexity="high", confidence=0.2, evidence_score=0.1,
    )

    assert low_confidence.selected_tier == "premium"
    assert "low_confidence_with_usable_evidence" in low_confidence.reasons
    assert missing_evidence.selected_tier == "standard"
    assert missing_evidence.premium_model_used is False
    assert "evidence_limited_no_premium_escalation" in missing_evidence.reasons


def test_missing_paid_credentials_fall_back_without_building_paid_provider():
    router = ModelRouter(_settings(deepseek_key="", kimi_key=""))
    decision = _decide(router, task="agentic_workflow", complexity="high", evidence_score=1.0)
    assert decision.selected_tier == "cheap"
    assert decision.provider == "openrouter"
    assert decision.fallback_used is True
    assert decision.premium_model_used is False


def test_gateway_logs_selected_route_and_premium_usage_without_network_calls():
    base = FakeProvider("openrouter", "openrouter/free")
    gateway = LLMGateway(provider=base)
    gateway.model_router = ModelRouter(_settings())
    gateway._build_provider = lambda provider_name=None, model=None: FakeProvider(provider_name, model)
    gateway._provider_cache = {(base.provider_name, base.model): base}
    repository = CapturingRepository()
    gateway.request_repository = repository

    response = gateway.generate_sync(
        [{"role": "user", "content": "Handle a complex supported case"}],
        task="agentic_workflow",
        token_context={
            "user_input": "Handle a complex supported case",
            "routing": {"complexity": "high", "confidence": 0.9, "evidence_score": 1.0},
        },
    )

    assert response.text == "response from kimi"
    logged = repository.requests[0]
    assert logged["provider"] == "kimi"
    assert logged["model"] == "kimi-k2.6"
    assert logged["metadata"]["routing"]["premium_model_used"] is True
    assert logged["metadata"]["routing"]["selected_tier"] == "premium"


def _settings(*, enabled=True, deepseek_key="configured", kimi_key="configured"):
    return SimpleNamespace(
        model_routing_enabled=enabled,
        routing_cheap_provider="openrouter",
        routing_cheap_model="openrouter/free",
        routing_standard_provider="deepseek",
        routing_standard_model="deepseek-v4-flash",
        routing_premium_provider="kimi",
        routing_premium_model="kimi-k2.6",
        routing_cheap_tasks="intent,extraction,product_search,orders,cart,escalation",
        routing_standard_tasks="simple_rag",
        routing_premium_tasks="complex_rag,agentic_workflow",
        routing_confidence_threshold=0.70,
        routing_evidence_threshold=0.65,
        openrouter_api_key="configured",
        deepseek_api_key=deepseek_key,
        kimi_api_key=kimi_key,
    )


def _decide(router, *, task, complexity, confidence=None, evidence_score=None):
    return router.decide(
        task=task,
        base_provider="openrouter",
        base_model="openrouter/free",
        estimated_input_tokens=100,
        input_budget=1000,
        tool_count=0,
        route_context={
            "complexity": complexity,
            "confidence": confidence,
            "evidence_score": evidence_score,
        },
    )


if __name__ == "__main__":
    test_routing_disabled_preserves_configured_provider()
    test_routes_by_task_and_complexity_with_cheap_first()
    test_confidence_and_evidence_quality_control_escalation()
    test_missing_paid_credentials_fall_back_without_building_paid_provider()
    test_gateway_logs_selected_route_and_premium_usage_without_network_calls()
    print("Model routing pipeline tests passed.")
