from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.base import LLMResponse  # noqa: E402
from core.llm.circuit_breaker import ProviderCircuitBreaker  # noqa: E402
from evaluation.test_provider_fallback import HTTPFailure, _gateway  # noqa: E402


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds: float):
        self.value += seconds


def test_repeated_failures_open_circuit_and_cooldown_allows_one_probe():
    clock = FakeClock()
    breaker = ProviderCircuitBreaker(_settings(), clock=clock)

    assert breaker.before_request("deepseek", "model-a").allowed is True
    first = breaker.record_failure("deepseek", "model-a")
    assert first.state == "closed"
    second = breaker.record_failure("deepseek", "model-a")
    assert second.state == "open"

    blocked = breaker.before_request("deepseek", "model-a")
    assert blocked.allowed is False
    assert blocked.reason == "cooldown_active"

    clock.advance(31)
    probe = breaker.before_request("deepseek", "model-a")
    concurrent_probe = breaker.before_request("deepseek", "model-a")
    assert probe.allowed is True
    assert probe.state == "half_open"
    assert concurrent_probe.allowed is False
    assert concurrent_probe.reason == "half_open_probe_in_flight"

    recovered = breaker.record_success("deepseek", "model-a")
    assert recovered.state == "closed"
    assert recovered.consecutive_failures == 0


def test_gateway_routes_to_alternative_while_primary_circuit_is_open_then_retries_primary():
    clock = FakeClock()
    gateway, primary, fallback, repository = _gateway(HTTPFailure(500))
    primary.outcomes = [HTTPFailure(500), HTTPFailure(500), LLMResponse(text="primary recovered")]
    fallback.outcomes = [
        LLMResponse(text="fallback success"),
        LLMResponse(text="fallback success"),
        LLMResponse(text="fallback success"),
    ]
    gateway.circuit_breaker = ProviderCircuitBreaker(_settings(), clock=clock)

    assert gateway.generate_sync([{"role": "user", "content": "one"}], task="orders").text == "fallback success"
    assert gateway.generate_sync([{"role": "user", "content": "two"}], task="orders").text == "fallback success"
    assert primary.calls == 2
    assert gateway.circuit_breaker.snapshot()["openrouter:openrouter/free"]["state"] == "open"

    assert gateway.generate_sync([{"role": "user", "content": "three"}], task="orders").text == "fallback success"
    assert primary.calls == 2
    third_final = repository.requests[-1]["metadata"]["fallback"]
    assert third_final["attempts"][0]["status"] == "skipped"
    assert third_final["attempts"][0]["failure"]["category"] == "circuit_open"

    clock.advance(31)
    response = gateway.generate_sync([{"role": "user", "content": "four"}], task="orders")
    assert response.text == "primary recovered"
    assert primary.calls == 3
    assert gateway.circuit_breaker.snapshot()["openrouter:openrouter/free"]["state"] == "closed"
    fourth_final = repository.requests[-1]["metadata"]["fallback"]
    assert fourth_final["fallback_used"] is False
    assert fourth_final["attempts"][0]["circuit"]["before"]["state"] == "half_open"


def test_circuit_health_is_isolated_per_provider_and_model():
    breaker = ProviderCircuitBreaker(_settings())
    breaker.record_failure("deepseek", "model-a")
    breaker.record_failure("deepseek", "model-a")

    assert breaker.before_request("deepseek", "model-a").allowed is False
    assert breaker.before_request("deepseek", "model-b").allowed is True
    assert breaker.before_request("kimi", "model-a").allowed is True


def _settings():
    return SimpleNamespace(
        circuit_breaker_enabled=True,
        circuit_breaker_failure_threshold=2,
        circuit_breaker_cooldown_seconds=30.0,
    )


if __name__ == "__main__":
    test_repeated_failures_open_circuit_and_cooldown_allows_one_probe()
    test_gateway_routes_to_alternative_while_primary_circuit_is_open_then_retries_primary()
    test_circuit_health_is_isolated_per_provider_and_model()
    print("Circuit breaker pipeline tests passed.")
