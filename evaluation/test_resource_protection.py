from pathlib import Path
from types import SimpleNamespace
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import RequestContext  # noqa: E402
from core.llm.base import LLMResponse  # noqa: E402
from core.llm.gateway import LLMGateway  # noqa: E402
from core.resource_protection import (  # noqa: E402
    ResourceLimitExceeded,
    ResourceLimits,
    ResourceProtectionService,
    resource_guard_context,
)


def _limits(**overrides):
    values = {
        "max_input_tokens": 100,
        "max_output_tokens": 20,
        "max_tool_calls": 2,
        "max_agent_steps": 2,
        "max_agent_runtime_seconds": 5,
        "max_request_cost_usd": 0.01,
        "max_input_price_per_million": 0,
        "max_output_price_per_million": 0,
        "user_rate_limit_requests": 3,
        "user_rate_limit_window_seconds": 60,
        "tenant_daily_request_quota": 10,
        "tenant_daily_token_quota": 1000,
        "tenant_daily_cost_quota_usd": 1,
        "expensive_repeat_limit": 2,
        "expensive_repeat_window_seconds": 300,
    }
    values.update(overrides)
    return ResourceLimits(**values)


def _service(**overrides):
    return ResourceProtectionService(limits=_limits(**overrides), use_postgres=False)


def _context(session="session-a", tenant="tenant-a", request=""):
    return RequestContext(session_id=session, tenant_id=tenant, request_id=request)


def test_input_and_output_limits():
    service = _service(max_input_tokens=5, max_output_tokens=10)
    try:
        service.begin_request("word " * 20, _context())
        raise AssertionError("oversized input should be rejected")
    except ResourceLimitExceeded as exc:
        assert exc.code == "max_input_tokens"

    guard = _service(max_output_tokens=10).begin_request("hello", _context(), workflow="product_search")
    bounded = guard.bound_response("long response sentence. " * 30)
    assert "Truncated" in bounded
    assert guard.output_tokens <= 10


def test_agent_step_tool_runtime_and_cost_limits():
    guard = _service().begin_request("hello", _context(), workflow="agent_loop")
    accounting = SimpleNamespace(total_input_tokens=10, output_limit=10)
    assert guard.before_llm(accounting) == 10
    guard.before_llm(accounting)
    try:
        guard.before_llm(accounting)
        raise AssertionError("agent steps should be bounded")
    except ResourceLimitExceeded as exc:
        assert exc.code == "max_agent_steps"

    tool_guard = _service().begin_request("tools", _context("tools"), workflow="agent_loop")
    tool_guard.before_tool_batch(2)
    tool_guard.before_tool("a")
    tool_guard.before_tool("b")
    try:
        tool_guard.before_tool("c")
        raise AssertionError("tool calls should be bounded")
    except ResourceLimitExceeded as exc:
        assert exc.code == "max_tool_calls"

    cost_guard = _service(max_request_cost_usd=0.001).begin_request("cost", _context("cost"), workflow="agent_loop")
    try:
        cost_guard.after_llm(
            SimpleNamespace(usage={"cost_usd": 0.002}),
            SimpleNamespace(output_tokens=3, total_input_tokens=5),
        )
        raise AssertionError("request cost should be bounded")
    except ResourceLimitExceeded as exc:
        assert exc.code == "max_request_cost"

    runtime_guard = _service(max_agent_runtime_seconds=1).begin_request("runtime", _context("runtime"), workflow="agent_loop")
    runtime_guard.started_at = time.monotonic() - 2
    try:
        runtime_guard.check_runtime()
        raise AssertionError("runtime should be bounded")
    except ResourceLimitExceeded as exc:
        assert exc.code == "max_runtime"


def test_rate_tenant_workflow_and_repetition_limits():
    service = _service(user_rate_limit_requests=2, expensive_repeat_limit=10)
    for query in ("hello one", "hello two"):
        guard = service.begin_request(query, _context(), workflow="product_search")
        service.finish_request(guard)
    try:
        service.begin_request("hello three", _context(), workflow="product_search")
        raise AssertionError("user rate limit should block")
    except ResourceLimitExceeded as exc:
        assert exc.code == "user_rate_limit"

    tenant_service = _service(tenant_daily_request_quota=2, user_rate_limit_requests=10)
    for index in range(2):
        guard = tenant_service.begin_request(
            f"tenant request {index}", _context(session=f"user-{index}"), workflow="product_search"
        )
        tenant_service.finish_request(guard)
    try:
        tenant_service.begin_request("tenant third", _context("user-3"), workflow="product_search")
        raise AssertionError("tenant quota should block")
    except ResourceLimitExceeded as exc:
        assert exc.code == "tenant_request_quota"

    workflow_service = ResourceProtectionService(
        limits=_limits(user_rate_limit_requests=10),
        use_postgres=False,
        workflow_limits={"product_search": 1},
    )
    guard = workflow_service.begin_request("first search", _context(), workflow="product_search")
    workflow_service.finish_request(guard)
    try:
        workflow_service.begin_request("second search", _context(), workflow="product_search")
        raise AssertionError("workflow rate limit should block")
    except ResourceLimitExceeded as exc:
        assert exc.code == "workflow_rate_limit"

    repeat_service = _service(user_rate_limit_requests=10, expensive_repeat_limit=2)
    for _ in range(2):
        guard = repeat_service.begin_request("What is the return policy?", _context(), workflow="rag_policy")
        repeat_service.finish_request(guard)
    try:
        repeat_service.begin_request("  what IS the return policy? ", _context(), workflow="rag_policy")
        raise AssertionError("repetitive expensive request should block")
    except ResourceLimitExceeded as exc:
        assert exc.code == "repetitive_expensive_request"


def test_token_cost_quotas_and_preflight_cost():
    token_service = _service(
        user_rate_limit_requests=10,
        tenant_daily_token_quota=5,
        max_input_tokens=100,
    )
    guard = token_service.begin_request("one two", _context(), workflow="product_search")
    guard.output_tokens = 2
    token_service.finish_request(guard)
    try:
        token_service.begin_request("three four", _context("second"), workflow="product_search")
        raise AssertionError("tenant token quota should block")
    except ResourceLimitExceeded as exc:
        assert exc.code == "tenant_token_quota"

    cost_service = _service(
        max_request_cost_usd=1,
        max_input_price_per_million=100_000,
        max_output_price_per_million=0,
        tenant_daily_cost_quota_usd=0.15,
        user_rate_limit_requests=10,
    )
    guard = cost_service.begin_request("a", _context(), workflow="product_search")
    guard.cost_usd = 0.1
    cost_service.finish_request(guard)
    try:
        cost_service.begin_request("b", _context("cost-user"), workflow="product_search")
        raise AssertionError("tenant cost quota should block")
    except ResourceLimitExceeded as exc:
        assert exc.code == "tenant_cost_quota"

    preflight = _service(
        max_request_cost_usd=0.001,
        max_input_price_per_million=100,
        max_output_price_per_million=100,
    ).begin_request("cost", _context("preflight"), workflow="agent_loop")
    try:
        preflight.before_llm(SimpleNamespace(total_input_tokens=10, output_limit=10))
        raise AssertionError("estimated request cost should block before the LLM call")
    except ResourceLimitExceeded as exc:
        assert exc.code == "max_request_cost"


def test_gateway_forces_output_limit():
    class FakeProvider:
        provider_name = "fake"
        model = "fake-model"

        def __init__(self):
            self.max_tokens = None
            self.timeout = None

        def generate_sync(self, messages, tools=None, temperature=None, **kwargs):
            self.max_tokens = kwargs.get("max_tokens")
            self.timeout = kwargs.get("timeout")
            return LLMResponse(text="short", usage={"input_tokens": 2, "output_tokens": 1})

    class NullRepository:
        def insert_request(self, **_payload):
            return None

    provider = FakeProvider()
    gateway = LLMGateway(provider=provider)
    gateway.request_repository = NullRepository()
    guard = _service(max_output_tokens=7).begin_request(
        "hello", _context("gateway"), workflow="agent_loop"
    )
    with resource_guard_context(guard):
        gateway.generate_sync(
            [{"role": "user", "content": "hello"}],
            max_tokens=999,
            token_context={"user_input": "hello"},
        )
    assert provider.max_tokens == 7
    assert 0 < provider.timeout <= guard.limits.max_agent_runtime_seconds
    assert guard.agent_steps == 1


if __name__ == "__main__":
    test_input_and_output_limits()
    test_agent_step_tool_runtime_and_cost_limits()
    test_rate_tenant_workflow_and_repetition_limits()
    test_token_cost_quotas_and_preflight_cost()
    test_gateway_forces_output_limit()
    print("Resource protection tests passed.")
