import asyncio
import time
from typing import Any

from configs import get_settings
from core.llm.base import LLMProvider, LLMResponse, Message, StructuredSchema, ToolDefinition
from core.llm.circuit_breaker import CircuitOpenError, ProviderCircuitBreaker
from core.llm.model_routing import ModelRouter, RoutingDecision
from core.llm.provider_fallback import (
    ProviderFallbackExhausted,
    ProviderFallbackPolicy,
    validate_provider_response,
)
from core.llm.providers import DeepSeekProvider, KimiProvider, OllamaProvider, OpenRouterProvider
from core.observability import current_trace_ids, observed_span, record_trace_event
from core.optimization import account_llm_context, estimate_tokens
from core.privacy import redact_for_logs
from core.prompts import get_system_prompt_metadata
from core.resource_protection import ResourceLimitExceeded, active_resource_guard
from core.repositories.llm_request_repository import LLMRequestRepository


class LLMGateway:
    """Application-facing LLM gateway that delegates to the configured provider."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or self._build_provider()
        self.model_router = ModelRouter(get_settings())
        self.fallback_policy = ProviderFallbackPolicy(get_settings())
        self.circuit_breaker = ProviderCircuitBreaker(get_settings())
        self._provider_cache = {(self.provider_name, self.model or ""): self.provider}
        self.request_repository = LLMRequestRepository()

    @property
    def provider_name(self) -> str:
        return getattr(self.provider, "provider_name", self.provider.__class__.__name__.lower())

    @property
    def model(self) -> str | None:
        return getattr(self.provider, "model", None)

    @property
    def model_version(self) -> str | None:
        return getattr(self.provider, "model_version", None)

    @property
    def model_metadata(self) -> dict[str, Any]:
        governance = getattr(self.provider, "model_governance", None)
        if governance is not None:
            return governance.metadata()
        return {
            "provider": self.provider_name,
            "model": self.model or "",
            "model_version": getattr(self.provider, "model_version", None) or f"alias:{self.model or ''}",
            "pinned": False,
            "alias": True,
            "source": "provider_metadata_unavailable",
        }

    @property
    def client(self):
        return getattr(self.provider, "client", None)

    def configure(
        self,
        provider_name: str,
        model: str | None = None,
    ) -> None:
        """Switch the active provider at runtime without touching business code."""
        self.provider = self._build_provider(provider_name=provider_name, model=model)
        self.model_router = ModelRouter(get_settings())
        self.fallback_policy = ProviderFallbackPolicy(get_settings())
        self._provider_cache = {(self.provider_name, self.model or ""): self.provider}

    def _build_provider(
        self,
        provider_name: str | None = None,
        model: str | None = None,
    ) -> LLMProvider:
        settings = get_settings()
        provider_name = (provider_name or settings.llm_provider).strip().lower()
        if provider_name == "openrouter":
            return OpenRouterProvider(model=model)
        if provider_name == "ollama":
            return OllamaProvider(model=model)
        if provider_name == "deepseek":
            return DeepSeekProvider(model=model)
        if provider_name in {"kimi", "moonshot"}:
            return KimiProvider(model=model)
        supported = "openrouter, ollama, deepseek, kimi"
        raise ValueError(f"Unsupported LLM_PROVIDER {provider_name!r}. Supported values: {supported}.")

    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        task: str = "agentic_workflow",
        token_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        accounting = self._account_context(messages, tools, task, token_context, provider=self.provider)
        provider, routing = self._route_provider(task, accounting, tools, token_context)
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate",
            attributes=self._span_attributes(
                tools, structured=False, accounting=accounting, provider=provider, routing=routing,
            ),
        ) as span:
            try:
                response, actual_provider, accounting, fallback_attempts = await self._invoke_async_with_fallback(
                    provider,
                    messages=messages,
                    tools=tools,
                    task=task,
                    token_context=token_context,
                    kwargs=kwargs,
                    structured=False,
                    routing=routing,
                    operation=lambda candidate, call_kwargs: candidate.generate(
                        messages, tools=tools, temperature=temperature, **call_kwargs
                    ),
                )
                latency_ms = _latency_ms(start)
                accounting = self._with_output(accounting, response)
                self._complete_call(response, accounting)
                span.set_attributes(
                    **self._usage_attributes(response, latency_ms, actual_provider),
                    provider=_provider_name(actual_provider),
                    model=_provider_model(actual_provider),
                    token_breakdown=accounting.to_dict(),
                    fallback=_fallback_summary(provider, actual_provider, fallback_attempts),
                )
                self._log_request(
                    messages, tools, response, "success", latency_ms=latency_ms,
                    accounting=accounting, token_context=token_context, provider=actual_provider, routing=routing,
                    metadata={"fallback": _fallback_summary(provider, actual_provider, fallback_attempts)},
                )
                return response
            except ProviderFallbackExhausted as exc:
                raise exc.original_error
            except Exception as exc:
                self._log_request(
                    messages, tools, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    accounting=accounting, token_context=token_context, provider=provider, routing=routing,
                )
                raise

    async def generate_structured(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        task: str = "extraction",
        token_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        accounting = self._account_context(messages, None, task, token_context, provider=self.provider)
        provider, routing = self._route_provider(task, accounting, None, token_context)
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate_structured",
            attributes=self._span_attributes(
                None, structured=True, accounting=accounting, provider=provider, routing=routing,
            ),
        ) as span:
            try:
                response, actual_provider, accounting, fallback_attempts = await self._invoke_async_with_fallback(
                    provider,
                    messages=messages,
                    tools=None,
                    task=task,
                    token_context=token_context,
                    kwargs=kwargs,
                    structured=True,
                    routing=routing,
                    operation=lambda candidate, call_kwargs: candidate.generate_structured(
                        messages, schema=schema, temperature=temperature, **call_kwargs
                    ),
                )
                latency_ms = _latency_ms(start)
                accounting = self._with_structured_output(accounting, response)
                self._complete_call(response, accounting)
                span.set_attributes(
                    latency_ms=latency_ms,
                    tokens_unavailable=True,
                    token_breakdown=accounting.to_dict(),
                    provider=_provider_name(actual_provider),
                    model=_provider_model(actual_provider),
                    fallback=_fallback_summary(provider, actual_provider, fallback_attempts),
                    **self._cost_attributes({}, actual_provider),
                )
                self._log_request(
                    messages, None, None, "success", latency_ms=latency_ms,
                    accounting=accounting, token_context=token_context, provider=actual_provider, routing=routing,
                    metadata={
                        "structured": True,
                        "fallback": _fallback_summary(provider, actual_provider, fallback_attempts),
                    },
                )
                return response
            except ProviderFallbackExhausted as exc:
                raise exc.original_error
            except Exception as exc:
                self._log_request(
                    messages, None, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    metadata={"structured": True}, accounting=accounting, token_context=token_context,
                    provider=provider, routing=routing,
                )
                raise

    def generate_sync(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        task: str = "agentic_workflow",
        token_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        accounting = self._account_context(messages, tools, task, token_context, provider=self.provider)
        provider, routing = self._route_provider(task, accounting, tools, token_context)
        if not hasattr(provider, "generate_sync"):
            return asyncio.run(self.generate(
                messages,
                tools=tools,
                temperature=temperature,
                task=task,
                token_context=token_context,
                **kwargs,
            ))
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate",
            attributes=self._span_attributes(
                tools, structured=False, accounting=accounting, provider=provider, routing=routing,
            ),
        ) as span:
            try:
                response, actual_provider, accounting, fallback_attempts = self._invoke_sync_with_fallback(
                    provider,
                    messages=messages,
                    tools=tools,
                    task=task,
                    token_context=token_context,
                    kwargs=kwargs,
                    structured=False,
                    routing=routing,
                    operation=lambda candidate, call_kwargs: candidate.generate_sync(
                        messages, tools=tools, temperature=temperature, **call_kwargs
                    ),
                )
                latency_ms = _latency_ms(start)
                accounting = self._with_output(accounting, response)
                self._complete_call(response, accounting)
                span.set_attributes(
                    **self._usage_attributes(response, latency_ms, actual_provider),
                    provider=_provider_name(actual_provider),
                    model=_provider_model(actual_provider),
                    token_breakdown=accounting.to_dict(),
                    fallback=_fallback_summary(provider, actual_provider, fallback_attempts),
                )
                self._log_request(
                    messages, tools, response, "success", latency_ms=latency_ms,
                    accounting=accounting, token_context=token_context, provider=actual_provider, routing=routing,
                    metadata={"fallback": _fallback_summary(provider, actual_provider, fallback_attempts)},
                )
                return response
            except ProviderFallbackExhausted as exc:
                raise exc.original_error
            except Exception as exc:
                self._log_request(
                    messages, tools, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    accounting=accounting, token_context=token_context, provider=provider, routing=routing,
                )
                raise

    def generate_structured_sync(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        task: str = "extraction",
        token_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        accounting = self._account_context(messages, None, task, token_context, provider=self.provider)
        provider, routing = self._route_provider(task, accounting, None, token_context)
        if not hasattr(provider, "generate_structured_sync"):
            return asyncio.run(self.generate_structured(
                messages,
                schema=schema,
                temperature=temperature,
                task=task,
                token_context=token_context,
                **kwargs,
            ))
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate_structured",
            attributes=self._span_attributes(
                None, structured=True, accounting=accounting, provider=provider, routing=routing,
            ),
        ) as span:
            try:
                response, actual_provider, accounting, fallback_attempts = self._invoke_sync_with_fallback(
                    provider,
                    messages=messages,
                    tools=None,
                    task=task,
                    token_context=token_context,
                    kwargs=kwargs,
                    structured=True,
                    routing=routing,
                    operation=lambda candidate, call_kwargs: candidate.generate_structured_sync(
                        messages, schema=schema, temperature=temperature, **call_kwargs
                    ),
                )
                latency_ms = _latency_ms(start)
                accounting = self._with_structured_output(accounting, response)
                self._complete_call(response, accounting)
                span.set_attributes(
                    latency_ms=latency_ms,
                    tokens_unavailable=True,
                    token_breakdown=accounting.to_dict(),
                    provider=_provider_name(actual_provider),
                    model=_provider_model(actual_provider),
                    fallback=_fallback_summary(provider, actual_provider, fallback_attempts),
                    **self._cost_attributes({}, actual_provider),
                )
                self._log_request(
                    messages, None, None, "success", latency_ms=latency_ms,
                    accounting=accounting, token_context=token_context, provider=actual_provider, routing=routing,
                    metadata={
                        "structured": True,
                        "fallback": _fallback_summary(provider, actual_provider, fallback_attempts),
                    },
                )
                return response
            except ProviderFallbackExhausted as exc:
                raise exc.original_error
            except Exception as exc:
                self._log_request(
                    messages, None, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    metadata={"structured": True}, accounting=accounting, token_context=token_context,
                    provider=provider, routing=routing,
                )
                raise

    def _log_request(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        response: LLMResponse | None,
        status: str,
        error_message: str = "",
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
        accounting=None,
        token_context: dict[str, Any] | None = None,
        provider: LLMProvider | None = None,
        routing: RoutingDecision | None = None,
    ) -> None:
        provider = provider or self.provider
        usage = response.usage if response and response.usage else {}
        cost = self._cost_attributes(usage, provider)
        trace_ids = current_trace_ids()
        token_context = token_context or {}
        provider_name = _provider_name(provider)
        model = _provider_model(provider)
        model_metadata = _provider_metadata(provider)
        self.request_repository.insert_request(
            provider=provider_name,
            model=model,
            model_version=_provider_model_version(provider),
            model_metadata=response.model_metadata if response and response.model_metadata else model_metadata,
            request_messages=redact_for_logs(_serializable_messages(messages)),
            request_tools=tools or [],
            response_text=redact_for_logs(response.text if response else ""),
            response_tool_calls=redact_for_logs([
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in (response.tool_calls if response else [])
            ]),
            status=status,
            error_message=redact_for_logs(error_message),
            latency_ms=latency_ms,
            usage=usage,
            cost_usd=cost["cost_usd"],
            cost_source=cost["cost_source"],
            request_id=trace_ids["request_id"],
            trace_id=trace_ids["trace_id"],
            token_breakdown=accounting.to_dict() if accounting else {},
            prompt_metadata=token_context.get("prompt_metadata") or get_system_prompt_metadata(),
            metadata={
                **(metadata or {}),
                "task": accounting.task if accounting else "",
                "routing": routing.metadata() if routing else {},
            },
        )

    def _span_attributes(
        self,
        tools: list[ToolDefinition] | None,
        *,
        structured: bool,
        accounting,
        provider: LLMProvider,
        routing: RoutingDecision,
    ) -> dict[str, Any]:
        return {
            "provider": _provider_name(provider),
            "model": _provider_model(provider),
            "model_version": _provider_model_version(provider),
            "structured": structured,
            "tools_exposed": len(tools or []),
            "task": accounting.task,
            "input_budget": accounting.input_budget,
            "output_limit": accounting.output_limit,
            "estimated_input_tokens": accounting.total_input_tokens,
            "context_utilization_ratio": accounting.context_utilization_ratio,
            "within_budget": accounting.within_budget,
            "routing": routing.metadata(),
            "premium_model_used": routing.premium_model_used,
        }

    def _account_context(
        self,
        messages,
        tools,
        task: str,
        token_context: dict[str, Any] | None,
        *,
        provider: LLMProvider,
    ):
        context = dict(token_context or _infer_token_context(messages))
        return account_llm_context(
            task=task,
            system_prompt=context.get("system_prompt", ""),
            user_input=context.get("user_input", ""),
            conversation=context.get("conversation", ""),
            retrieval_context=context.get("retrieval_context", ""),
            tools=tools,
            provider_prompt_cache_eligible=bool(getattr(provider, "supports_prompt_caching", False)),
        )

    def _route_provider(
        self,
        task: str,
        accounting,
        tools: list[ToolDefinition] | None,
        token_context: dict[str, Any] | None,
    ) -> tuple[LLMProvider, RoutingDecision]:
        context = token_context or {}
        decision = self.model_router.decide(
            task=task,
            base_provider=self.provider_name,
            base_model=self.model or "",
            estimated_input_tokens=accounting.total_input_tokens,
            input_budget=accounting.input_budget,
            tool_count=len(tools or []),
            route_context=context.get("routing") or {},
        )
        if not decision.enabled or (
            decision.provider == self.provider_name and decision.model == (self.model or "")
        ):
            return self.provider, decision
        key = (decision.provider, decision.model)
        if key not in self._provider_cache:
            self._provider_cache[key] = self._build_provider(decision.provider, decision.model)
        return self._provider_cache[key], decision

    def _fallback_candidates(self, primary: LLMProvider) -> list[LLMProvider]:
        candidates = []
        for target in self.fallback_policy.targets(_provider_name(primary), _provider_model(primary)):
            key = (target.provider, target.model)
            if key == (_provider_name(primary), _provider_model(primary)):
                candidate = primary
            else:
                if key not in self._provider_cache:
                    self._provider_cache[key] = self._build_provider(target.provider, target.model)
                candidate = self._provider_cache[key]
            candidates.append(candidate)
        return candidates

    async def _invoke_async_with_fallback(
        self,
        primary: LLMProvider,
        *,
        messages,
        tools,
        task: str,
        token_context,
        kwargs: dict[str, Any],
        structured: bool,
        operation,
        routing: RoutingDecision,
    ):
        attempts = []
        candidates = self._fallback_candidates(primary)
        for index, candidate in enumerate(candidates, start=1):
            circuit_before = self.circuit_breaker.before_request(
                _provider_name(candidate), _provider_model(candidate)
            )
            if not circuit_before.allowed:
                attempt = _fallback_attempt(
                    index, candidate, "skipped", 0,
                    {"category": "circuit_open", "retryable": True},
                    circuit={"before": circuit_before.metadata()},
                )
                attempts.append(attempt)
                record_trace_event(
                    "llm", "llm.circuit_open", status="blocked", attributes=attempt,
                )
                continue
            accounting = self._account_context(
                messages, tools, task, token_context, provider=candidate,
            )
            call_kwargs = dict(kwargs)
            self._apply_output_limit(call_kwargs, self._prepare_call(accounting))
            started = time.perf_counter()
            try:
                response = await operation(candidate, call_kwargs)
                validate_provider_response(response, structured=structured)
                circuit_after = self.circuit_breaker.record_success(
                    _provider_name(candidate), _provider_model(candidate)
                )
                attempts.append(_fallback_attempt(
                    index, candidate, "success", _latency_ms(started),
                    circuit={"before": circuit_before.metadata(), "after": circuit_after.metadata()},
                ))
                return response, candidate, accounting, attempts
            except Exception as exc:
                classification = self.fallback_policy.classify(exc)
                circuit_after = (
                    self.circuit_breaker.record_failure(
                        _provider_name(candidate), _provider_model(candidate)
                    )
                    if classification.retryable
                    else self.circuit_breaker.record_success(
                        _provider_name(candidate), _provider_model(candidate)
                    )
                )
                attempt = _fallback_attempt(
                    index, candidate, "error", _latency_ms(started), classification.metadata(),
                    circuit={"before": circuit_before.metadata(), "after": circuit_after.metadata()},
                )
                attempts.append(attempt)
                self._log_request(
                    messages, tools, None, "error", error_message=str(exc),
                    latency_ms=attempt["latency_ms"], accounting=accounting,
                    token_context=token_context, provider=candidate, routing=routing,
                    metadata={"fallback": {"attempt": attempt, "will_retry": (
                        classification.retryable and index < len(candidates)
                    )}},
                )
                if not classification.retryable or index >= len(candidates):
                    raise ProviderFallbackExhausted(exc, attempts) from exc
                await asyncio.sleep(self.fallback_policy.settings.provider_fallback_backoff_seconds * index)
        raise ProviderFallbackExhausted(
            CircuitOpenError("All provider candidates currently have an open circuit."), attempts
        )

    def _invoke_sync_with_fallback(
        self,
        primary: LLMProvider,
        *,
        messages,
        tools,
        task: str,
        token_context,
        kwargs: dict[str, Any],
        structured: bool,
        operation,
        routing: RoutingDecision,
    ):
        attempts = []
        candidates = self._fallback_candidates(primary)
        for index, candidate in enumerate(candidates, start=1):
            circuit_before = self.circuit_breaker.before_request(
                _provider_name(candidate), _provider_model(candidate)
            )
            if not circuit_before.allowed:
                attempt = _fallback_attempt(
                    index, candidate, "skipped", 0,
                    {"category": "circuit_open", "retryable": True},
                    circuit={"before": circuit_before.metadata()},
                )
                attempts.append(attempt)
                record_trace_event(
                    "llm", "llm.circuit_open", status="blocked", attributes=attempt,
                )
                continue
            accounting = self._account_context(
                messages, tools, task, token_context, provider=candidate,
            )
            call_kwargs = dict(kwargs)
            self._apply_output_limit(call_kwargs, self._prepare_call(accounting))
            started = time.perf_counter()
            try:
                response = operation(candidate, call_kwargs)
                validate_provider_response(response, structured=structured)
                circuit_after = self.circuit_breaker.record_success(
                    _provider_name(candidate), _provider_model(candidate)
                )
                attempts.append(_fallback_attempt(
                    index, candidate, "success", _latency_ms(started),
                    circuit={"before": circuit_before.metadata(), "after": circuit_after.metadata()},
                ))
                return response, candidate, accounting, attempts
            except Exception as exc:
                classification = self.fallback_policy.classify(exc)
                circuit_after = (
                    self.circuit_breaker.record_failure(
                        _provider_name(candidate), _provider_model(candidate)
                    )
                    if classification.retryable
                    else self.circuit_breaker.record_success(
                        _provider_name(candidate), _provider_model(candidate)
                    )
                )
                attempt = _fallback_attempt(
                    index, candidate, "error", _latency_ms(started), classification.metadata(),
                    circuit={"before": circuit_before.metadata(), "after": circuit_after.metadata()},
                )
                attempts.append(attempt)
                self._log_request(
                    messages, tools, None, "error", error_message=str(exc),
                    latency_ms=attempt["latency_ms"], accounting=accounting,
                    token_context=token_context, provider=candidate, routing=routing,
                    metadata={"fallback": {"attempt": attempt, "will_retry": (
                        classification.retryable and index < len(candidates)
                    )}},
                )
                if not classification.retryable or index >= len(candidates):
                    raise ProviderFallbackExhausted(exc, attempts) from exc
                time.sleep(self.fallback_policy.settings.provider_fallback_backoff_seconds * index)
        raise ProviderFallbackExhausted(
            CircuitOpenError("All provider candidates currently have an open circuit."), attempts
        )

    def _prepare_call(self, accounting) -> int:
        settings = get_settings()
        if accounting.total_input_tokens > settings.max_input_tokens:
            raise ResourceLimitExceeded("max_input_tokens", "Maximum LLM input tokens exceeded.")
        guard = active_resource_guard()
        if guard is not None:
            return guard.before_llm(accounting)
        return min(accounting.output_limit, settings.max_output_tokens)

    @staticmethod
    def _complete_call(response: Any, accounting) -> None:
        guard = active_resource_guard()
        if guard is not None:
            guard.after_llm(response, accounting)

    @staticmethod
    def _apply_output_limit(kwargs: dict[str, Any], allowed: int) -> None:
        try:
            requested = int(kwargs.get("max_tokens", allowed))
        except (TypeError, ValueError):
            requested = allowed
        kwargs["max_tokens"] = min(max(1, requested), allowed)
        guard = active_resource_guard()
        if guard is not None:
            try:
                requested_timeout = float(kwargs.get("timeout", guard.remaining_seconds))
            except (TypeError, ValueError):
                requested_timeout = guard.remaining_seconds
            kwargs["timeout"] = min(max(0.1, requested_timeout), guard.remaining_seconds)

    @staticmethod
    def _with_output(accounting, response: LLMResponse):
        output_tokens = _usage_value(response.usage or {}, "output_tokens", "completion_tokens")
        if output_tokens is None:
            output_tokens = estimate_tokens(response.text)
        values = accounting.to_dict()
        values["output_tokens"] = output_tokens
        return accounting.__class__(**values)

    @staticmethod
    def _with_structured_output(accounting, response: Any):
        value = response.model_dump(exclude_none=True) if hasattr(response, "model_dump") else response
        values = accounting.to_dict()
        values["output_tokens"] = estimate_tokens(value)
        return accounting.__class__(**values)

    def _usage_attributes(
        self,
        response: LLMResponse,
        latency_ms: int,
        provider: LLMProvider,
    ) -> dict[str, Any]:
        usage = response.usage or {}
        return {
            "latency_ms": latency_ms,
            "prompt_tokens": _usage_value(usage, "input_tokens", "prompt_tokens"),
            "completion_tokens": _usage_value(usage, "output_tokens", "completion_tokens"),
            "total_tokens": _usage_value(usage, "total_tokens"),
            **self._cost_attributes(usage, provider),
        }

    def _cost_attributes(
        self,
        usage: dict[str, Any],
        provider: LLMProvider | None = None,
    ) -> dict[str, Any]:
        provider = provider or self.provider
        for key in ("cost_usd", "cost", "total_cost"):
            if usage.get(key) is not None:
                try:
                    cost = float(usage[key])
                except (TypeError, ValueError):
                    continue
                if cost >= 0:
                    return {"cost_usd": cost, "cost_source": "provider"}
        provider_name = _provider_name(provider)
        model = _provider_model(provider)
        if provider_name == "ollama":
            return {"cost_usd": 0.0, "cost_source": "local"}
        if provider_name == "openrouter" and model.endswith("/free"):
            return {"cost_usd": 0.0, "cost_source": "free_model"}
        return {"cost_usd": None, "cost_source": "not_reported"}


def _latency_ms(start: float) -> int:
    return int(round((time.perf_counter() - start) * 1000))


def _provider_name(provider: LLMProvider) -> str:
    return getattr(provider, "provider_name", provider.__class__.__name__.lower())


def _provider_model(provider: LLMProvider) -> str:
    return getattr(provider, "model", None) or ""


def _provider_model_version(provider: LLMProvider) -> str:
    return getattr(provider, "model_version", None) or ""


def _provider_metadata(provider: LLMProvider) -> dict[str, Any]:
    governance = getattr(provider, "model_governance", None)
    if governance is not None:
        return governance.metadata()
    model = _provider_model(provider)
    return {
        "provider": _provider_name(provider),
        "model": model,
        "model_version": _provider_model_version(provider) or f"alias:{model}",
        "pinned": False,
        "alias": True,
        "source": "provider_metadata_unavailable",
    }


def _fallback_attempt(
    index: int,
    provider: LLMProvider,
    status: str,
    latency_ms: int,
    failure: dict[str, Any] | None = None,
    circuit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "attempt": index,
        "provider": _provider_name(provider),
        "model": _provider_model(provider),
        "status": status,
        "latency_ms": latency_ms,
        "failure": failure or {},
        "circuit": circuit or {},
    }


def _fallback_summary(
    primary: LLMProvider,
    actual: LLMProvider,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "fallback_triggered": len(attempts) > 1,
        "fallback_used": (
            _provider_name(primary), _provider_model(primary)
        ) != (
            _provider_name(actual), _provider_model(actual)
        ),
        "primary_provider": _provider_name(primary),
        "primary_model": _provider_model(primary),
        "final_provider": _provider_name(actual),
        "final_model": _provider_model(actual),
        "attempt_count": len(attempts),
        "attempts": attempts,
    }


def _usage_value(usage: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            return parsed if parsed >= 0 else None
    return None


def _serializable_messages(messages: list[Message]) -> list[dict[str, Any]]:
    serializable = []
    for message in messages:
        if isinstance(message, dict):
            serializable.append({"role": message.get("role"), "content": message.get("content", "")})
        else:
            serializable.append({
                "role": message.__class__.__name__,
                "content": getattr(message, "content", ""),
                "name": getattr(message, "name", None),
            })
    return serializable


def _infer_token_context(messages: list[Message]) -> dict[str, Any]:
    system_parts = []
    conversation_parts = []
    user_input = ""
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role", "")).lower()
            content = str(message.get("content", ""))
        else:
            role = message.__class__.__name__.lower()
            content = str(getattr(message, "content", ""))
        if "system" in role:
            system_parts.append(content)
        elif "human" in role or role == "user":
            if user_input:
                conversation_parts.append(user_input)
            user_input = content
        else:
            conversation_parts.append(content)
    return {
        "system_prompt": "\n".join(system_parts),
        "user_input": user_input,
        "conversation": "\n".join(conversation_parts),
        "retrieval_context": "",
    }


llm_gateway = LLMGateway()
