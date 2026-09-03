import time
from dataclasses import dataclass
from typing import Any

from core.optimization import estimate_tokens


WORKFLOW_REQUEST_LIMITS = {
    "agent_loop": 10,
    "rag_policy": 20,
    "product_search": 30,
    "order_status": 30,
    "confirmed_write_action": 10,
    "out_of_scope": 60,
}

EXPENSIVE_WORKFLOWS = {"agent_loop", "rag_policy"}


@dataclass(frozen=True)
class ResourceLimits:
    max_input_tokens: int
    max_output_tokens: int
    max_tool_calls: int
    max_agent_steps: int
    max_agent_runtime_seconds: int
    max_request_cost_usd: float
    max_input_price_per_million: float
    max_output_price_per_million: float
    user_rate_limit_requests: int
    user_rate_limit_window_seconds: int
    tenant_daily_request_quota: int
    tenant_daily_token_quota: int
    tenant_daily_cost_quota_usd: float
    expensive_repeat_limit: int
    expensive_repeat_window_seconds: int

    def __post_init__(self):
        positive = (
            "max_input_tokens",
            "max_output_tokens",
            "max_tool_calls",
            "max_agent_steps",
            "max_agent_runtime_seconds",
            "user_rate_limit_requests",
            "user_rate_limit_window_seconds",
            "tenant_daily_request_quota",
            "tenant_daily_token_quota",
            "expensive_repeat_limit",
            "expensive_repeat_window_seconds",
        )
        if any(getattr(self, field) <= 0 for field in positive):
            raise ValueError("Resource limit counts and windows must be positive.")
        if any(getattr(self, field) < 0 for field in (
            "max_request_cost_usd",
            "max_input_price_per_million",
            "max_output_price_per_million",
            "tenant_daily_cost_quota_usd",
        )):
            raise ValueError("Resource cost limits cannot be negative.")

    @classmethod
    def from_settings(cls, settings) -> "ResourceLimits":
        return cls(**{field: getattr(settings, field) for field in cls.__dataclass_fields__})


class ResourceLimitExceeded(RuntimeError):
    def __init__(self, code: str, detail: str, retry_after_seconds: int | None = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.retry_after_seconds = retry_after_seconds

    def user_message(self, language: str = "English") -> str:
        retry = ""
        if self.retry_after_seconds:
            retry = (
                f" Silakan coba lagi dalam sekitar {self.retry_after_seconds} detik."
                if language == "Indonesian"
                else f" Please try again in about {self.retry_after_seconds} seconds."
            )
        if language == "Indonesian":
            return "Permintaan dihentikan karena melewati batas penggunaan yang aman." + retry
        return "The request was stopped because it exceeded a safe usage limit." + retry


@dataclass
class RequestResourceGuard:
    limits: ResourceLimits
    request_id: str
    identity_key: str
    tenant_id: str
    session_id: str
    user_id: str | None
    workflow: str
    input_hash: str
    input_tokens: int
    started_at: float
    tool_calls: int = 0
    agent_steps: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cost_governance: dict[str, Any] | None = None

    def check_runtime(self) -> None:
        if self.elapsed_seconds > self.limits.max_agent_runtime_seconds:
            raise ResourceLimitExceeded("max_runtime", "Maximum agent runtime exceeded.")

    def before_llm(self, accounting) -> int:
        self.check_runtime()
        self.agent_steps += 1
        if self.agent_steps > self.limits.max_agent_steps:
            raise ResourceLimitExceeded("max_agent_steps", "Maximum agent steps exceeded.")
        if accounting.total_input_tokens > self.limits.max_input_tokens:
            raise ResourceLimitExceeded("max_input_tokens", "Maximum LLM input tokens exceeded.")
        output_limit = min(accounting.output_limit, self.limits.max_output_tokens)
        estimated_cost = (
            accounting.total_input_tokens * self.limits.max_input_price_per_million
            + output_limit * self.limits.max_output_price_per_million
        ) / 1_000_000
        if self.cost_usd + estimated_cost > self.limits.max_request_cost_usd:
            raise ResourceLimitExceeded("max_request_cost", "Preflight request cost exceeds the configured maximum.")
        return output_limit

    def after_llm(self, response: Any, accounting) -> None:
        output_tokens = max(0, int(accounting.output_tokens or 0))
        self.output_tokens += output_tokens
        usage = getattr(response, "usage", None) or {}
        cost_reported = False
        for key in ("cost_usd", "cost", "total_cost"):
            if usage.get(key) is not None:
                try:
                    self.cost_usd += max(0.0, float(usage[key]))
                    cost_reported = True
                except (TypeError, ValueError):
                    pass
                break
        if not cost_reported:
            self.cost_usd += (
                accounting.total_input_tokens * self.limits.max_input_price_per_million
                + output_tokens * self.limits.max_output_price_per_million
            ) / 1_000_000
        if self.cost_usd > self.limits.max_request_cost_usd:
            raise ResourceLimitExceeded("max_request_cost", "Maximum request cost exceeded.")
        self.check_runtime()

    def before_tool(self, _tool_name: str) -> None:
        self.check_runtime()
        self.tool_calls += 1
        if self.tool_calls > self.limits.max_tool_calls:
            raise ResourceLimitExceeded("max_tool_calls", "Maximum tool calls exceeded.")

    def before_tool_batch(self, count: int) -> None:
        self.check_runtime()
        if self.tool_calls + max(0, count) > self.limits.max_tool_calls:
            raise ResourceLimitExceeded("max_tool_calls", "Proposed tool batch exceeds the maximum tool calls.")

    def bound_response(self, response: str) -> str:
        if estimate_tokens(response) <= self.limits.max_output_tokens:
            self.output_tokens = max(self.output_tokens, estimate_tokens(response))
            return response
        suffix = "\n\n[Truncated]"
        low, high = 0, len(response)
        while low < high:
            middle = (low + high + 1) // 2
            if estimate_tokens(response[:middle] + suffix) <= self.limits.max_output_tokens:
                low = middle
            else:
                high = middle - 1
        bounded = response[:low].rstrip() + suffix
        self.output_tokens = max(self.output_tokens, estimate_tokens(bounded))
        return bounded

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def remaining_seconds(self) -> float:
        return max(0.1, self.limits.max_agent_runtime_seconds - self.elapsed_seconds)
