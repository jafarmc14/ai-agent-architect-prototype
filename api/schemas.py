from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "ai-agent-api"
    environment: str
    database_provider: str


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    environment: str
    database_provider: str
    provider: str
    model: str
    model_routing_enabled: bool
    provider_fallback_enabled: bool
    circuit_breaker_enabled: bool
    cost_governance_enabled: bool
    model_version: str | None = None
    model_governance: dict[str, Any] = Field(default_factory=dict)
    prompt: dict[str, Any] = Field(default_factory=dict)


class ConfigureLLMRequest(BaseModel):
    provider: str
    model: str | None = None


class ProviderOption(BaseModel):
    provider: str
    models: list[str] = Field(default_factory=list)


class ProviderOptionsResponse(BaseModel):
    options: dict[str, ProviderOption] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = "api-anonymous"
    auth_token: str | None = None


class ChatResponse(BaseModel):
    response: str
    request_id: str | None = None
    trace_id: str | None = None
    request_status: str | None = None
    request_latency_ms: int | None = None
    intent: str | None = None
    workflow: str | None = None
    use_agent_loop: bool | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    exposed_tools: list[str] = Field(default_factory=list)
    lifecycle: list[dict[str, Any]] = Field(default_factory=list)
    routing_structured: dict[str, Any] | None = None
    policy_decision_structured: dict[str, Any] | None = None
    escalation_decision: dict[str, Any] | None = None
    prompt: dict[str, Any] | None = None
    model_governance: dict[str, Any] | None = None
    claim_audit: dict[str, Any] | None = None
    hallucination_abstained: bool = False
    agent_loop_safety: dict[str, Any] | None = None
    resource_usage: dict[str, Any] | None = None
    resource_limit: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    exception: str | None = None
