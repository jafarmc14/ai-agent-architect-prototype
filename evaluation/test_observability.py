from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.llm.gateway as gateway_module  # noqa: E402
from core.auth import RequestContext  # noqa: E402
from core.llm.base import LLMResponse, extract_llm_usage  # noqa: E402
from core.llm.gateway import LLMGateway  # noqa: E402
from core.observability.service import ObservabilityService  # noqa: E402


class CapturingObservabilityRepository:
    def __init__(self):
        self.requests = {}
        self.spans = []

    def start_request(self, **payload):
        self.requests[payload["request_id"]] = {**payload, "status": "running"}

    def finish_request(self, **payload):
        self.requests[payload["request_id"]].update(payload)

    def insert_span(self, **payload):
        self.spans.append(payload)


class CapturingLLMRequestRepository:
    def __init__(self):
        self.requests = []

    def insert_request(self, **payload):
        self.requests.append(payload)


class FakeProvider:
    provider_name = "fake"
    model = "fake-model"
    model_version = "v1"
    client = None

    def generate_sync(self, messages, tools=None, temperature=None, **kwargs):
        return LLMResponse(
            text="observed response",
            usage={
                "input_tokens": 12,
                "output_tokens": 4,
                "total_tokens": 16,
                "cost_usd": 0.0025,
            },
        )


def test_request_lifecycle_has_correlated_stages():
    repository = CapturingObservabilityRepository()
    service = ObservabilityService(repository=repository)
    runtime_trace = {}

    with service.trace_request(
        "Find shoes for customer@example.com",
        RequestContext(session_id="observability-test", tenant_id="tenant-a"),
        runtime_trace,
    ) as request_trace:
        with service.span("intent", "intent.route", attributes={"intent": "PRODUCT_SEARCH"}):
            pass
        with service.span("tool", "tool.search_products", attributes={"query": "shoes"}):
            pass
        request_trace.complete("Two products found.", intent="PRODUCT_SEARCH", workflow="product_search")

    request = repository.requests[request_trace.request_id]
    assert request_trace.request_id == runtime_trace["request_id"]
    assert request_trace.trace_id == runtime_trace["trace_id"]
    assert request["status"] == "success"
    assert request["intent"] == "PRODUCT_SEARCH"
    assert "customer@example.com" not in request["request_input"]
    assert {span["stage"] for span in repository.spans} >= {"request", "intent", "tool", "response"}
    assert all(span["trace_id"] == request_trace.trace_id for span in repository.spans)


def test_llm_usage_cost_and_trace_ids_are_logged():
    trace_repository = CapturingObservabilityRepository()
    service = ObservabilityService(repository=trace_repository)
    llm_repository = CapturingLLMRequestRepository()
    gateway = LLMGateway(provider=FakeProvider())
    gateway.request_repository = llm_repository
    original_observed_span = gateway_module.observed_span
    gateway_module.observed_span = service.span
    try:
        with service.trace_request(
            "hello",
            RequestContext(session_id="llm-observability"),
            {},
        ) as request_trace:
            response = gateway.generate_sync([{"role": "user", "content": "hello"}])
            request_trace.complete(response.text)
    finally:
        gateway_module.observed_span = original_observed_span

    logged = llm_repository.requests[0]
    assert logged["request_id"] == request_trace.request_id
    assert logged["trace_id"] == request_trace.trace_id
    assert logged["usage"]["total_tokens"] == 16
    assert logged["cost_usd"] == 0.0025
    llm_span = next(span for span in trace_repository.spans if span["stage"] == "llm")
    assert llm_span["attributes"]["provider"] == "fake"
    assert llm_span["attributes"]["total_tokens"] == 16
    assert llm_span["attributes"]["cost_usd"] == 0.0025


def test_provider_usage_metadata_is_normalized():
    class RawResponse:
        usage_metadata = None
        response_metadata = {
            "token_usage": {"prompt_tokens": 7, "completion_tokens": 3},
            "cost": 0.001,
        }

    usage = extract_llm_usage(RawResponse())
    assert usage["input_tokens"] == 7
    assert usage["output_tokens"] == 3
    assert usage["total_tokens"] == 10
    assert usage["cost_usd"] == 0.001


if __name__ == "__main__":
    test_request_lifecycle_has_correlated_stages()
    test_llm_usage_cost_and_trace_ids_are_logged()
    test_provider_usage_metadata_is_normalized()
    print("Observability tests passed.")
