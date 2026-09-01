import asyncio
import time
from typing import Any

from configs import get_settings
from core.llm.base import LLMProvider, LLMResponse, Message, StructuredSchema, ToolDefinition
from core.llm.providers import OllamaProvider, OpenRouterProvider
from core.observability import current_trace_ids, observed_span
from core.optimization import account_llm_context, estimate_tokens
from core.privacy import redact_for_logs
from core.prompts import get_system_prompt_metadata
from core.repositories.llm_request_repository import LLMRequestRepository


class LLMGateway:
    """Application-facing LLM gateway that delegates to the configured provider."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or self._build_provider()
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
        supported = "openrouter, ollama"
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
        accounting = self._account_context(messages, tools, task, token_context)
        kwargs.setdefault("max_tokens", accounting.output_limit)
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate",
            attributes=self._span_attributes(tools, structured=False, accounting=accounting),
        ) as span:
            try:
                response = await self.provider.generate(messages, tools=tools, temperature=temperature, **kwargs)
                latency_ms = _latency_ms(start)
                accounting = self._with_output(accounting, response)
                span.set_attributes(**self._usage_attributes(response, latency_ms), token_breakdown=accounting.to_dict())
                self._log_request(
                    messages, tools, response, "success", latency_ms=latency_ms,
                    accounting=accounting, token_context=token_context,
                )
                return response
            except Exception as exc:
                self._log_request(
                    messages, tools, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    accounting=accounting, token_context=token_context,
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
        accounting = self._account_context(messages, None, task, token_context)
        kwargs.setdefault("max_tokens", accounting.output_limit)
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate_structured",
            attributes=self._span_attributes(None, structured=True, accounting=accounting),
        ) as span:
            try:
                response = await self.provider.generate_structured(messages, schema=schema, temperature=temperature, **kwargs)
                latency_ms = _latency_ms(start)
                accounting = self._with_structured_output(accounting, response)
                span.set_attributes(
                    latency_ms=latency_ms,
                    tokens_unavailable=True,
                    token_breakdown=accounting.to_dict(),
                    **self._cost_attributes({}),
                )
                self._log_request(
                    messages, None, None, "success", latency_ms=latency_ms, metadata={"structured": True},
                    accounting=accounting, token_context=token_context,
                )
                return response
            except Exception as exc:
                self._log_request(
                    messages, None, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    metadata={"structured": True}, accounting=accounting, token_context=token_context,
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
        if not hasattr(self.provider, "generate_sync"):
            return asyncio.run(self.generate(
                messages,
                tools=tools,
                temperature=temperature,
                task=task,
                token_context=token_context,
                **kwargs,
            ))
        accounting = self._account_context(messages, tools, task, token_context)
        kwargs.setdefault("max_tokens", accounting.output_limit)
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate",
            attributes=self._span_attributes(tools, structured=False, accounting=accounting),
        ) as span:
            try:
                response = self.provider.generate_sync(messages, tools=tools, temperature=temperature, **kwargs)
                latency_ms = _latency_ms(start)
                accounting = self._with_output(accounting, response)
                span.set_attributes(**self._usage_attributes(response, latency_ms), token_breakdown=accounting.to_dict())
                self._log_request(
                    messages, tools, response, "success", latency_ms=latency_ms,
                    accounting=accounting, token_context=token_context,
                )
                return response
            except Exception as exc:
                self._log_request(
                    messages, tools, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    accounting=accounting, token_context=token_context,
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
        if not hasattr(self.provider, "generate_structured_sync"):
            return asyncio.run(self.generate_structured(
                messages,
                schema=schema,
                temperature=temperature,
                task=task,
                token_context=token_context,
                **kwargs,
            ))
        accounting = self._account_context(messages, None, task, token_context)
        kwargs.setdefault("max_tokens", accounting.output_limit)
        start = time.perf_counter()
        with observed_span(
            "llm",
            "llm.generate_structured",
            attributes=self._span_attributes(None, structured=True, accounting=accounting),
        ) as span:
            try:
                response = self.provider.generate_structured_sync(messages, schema=schema, temperature=temperature, **kwargs)
                latency_ms = _latency_ms(start)
                accounting = self._with_structured_output(accounting, response)
                span.set_attributes(
                    latency_ms=latency_ms,
                    tokens_unavailable=True,
                    token_breakdown=accounting.to_dict(),
                    **self._cost_attributes({}),
                )
                self._log_request(
                    messages, None, None, "success", latency_ms=latency_ms, metadata={"structured": True},
                    accounting=accounting, token_context=token_context,
                )
                return response
            except Exception as exc:
                self._log_request(
                    messages, None, None, "error", error_message=str(exc), latency_ms=_latency_ms(start),
                    metadata={"structured": True}, accounting=accounting, token_context=token_context,
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
    ) -> None:
        usage = response.usage if response and response.usage else {}
        cost = self._cost_attributes(usage)
        trace_ids = current_trace_ids()
        token_context = token_context or {}
        self.request_repository.insert_request(
            provider=self.provider_name,
            model=self.model or "",
            model_version=self.model_version or "",
            model_metadata=response.model_metadata if response and response.model_metadata else self.model_metadata,
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
            metadata={**(metadata or {}), "task": accounting.task if accounting else ""},
        )

    def _span_attributes(self, tools: list[ToolDefinition] | None, *, structured: bool, accounting) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model or "",
            "model_version": self.model_version or "",
            "structured": structured,
            "tools_exposed": len(tools or []),
            "task": accounting.task,
            "input_budget": accounting.input_budget,
            "output_limit": accounting.output_limit,
            "estimated_input_tokens": accounting.total_input_tokens,
            "context_utilization_ratio": accounting.context_utilization_ratio,
            "within_budget": accounting.within_budget,
        }

    def _account_context(self, messages, tools, task: str, token_context: dict[str, Any] | None):
        context = dict(token_context or _infer_token_context(messages))
        return account_llm_context(
            task=task,
            system_prompt=context.get("system_prompt", ""),
            user_input=context.get("user_input", ""),
            conversation=context.get("conversation", ""),
            retrieval_context=context.get("retrieval_context", ""),
            tools=tools,
            provider_prompt_cache_eligible=bool(getattr(self.provider, "supports_prompt_caching", False)),
        )

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

    def _usage_attributes(self, response: LLMResponse, latency_ms: int) -> dict[str, Any]:
        usage = response.usage or {}
        return {
            "latency_ms": latency_ms,
            "prompt_tokens": _usage_value(usage, "input_tokens", "prompt_tokens"),
            "completion_tokens": _usage_value(usage, "output_tokens", "completion_tokens"),
            "total_tokens": _usage_value(usage, "total_tokens"),
            **self._cost_attributes(usage),
        }

    def _cost_attributes(self, usage: dict[str, Any]) -> dict[str, Any]:
        for key in ("cost_usd", "cost", "total_cost"):
            if usage.get(key) is not None:
                try:
                    cost = float(usage[key])
                except (TypeError, ValueError):
                    continue
                if cost >= 0:
                    return {"cost_usd": cost, "cost_source": "provider"}
        if self.provider_name == "ollama":
            return {"cost_usd": 0.0, "cost_source": "local"}
        if self.provider_name == "openrouter" and (self.model or "").endswith("/free"):
            return {"cost_usd": 0.0, "cost_source": "free_model"}
        return {"cost_usd": None, "cost_source": "not_reported"}


def _latency_ms(start: float) -> int:
    return int(round((time.perf_counter() - start) * 1000))


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
