import asyncio
import time
from typing import Any

from configs import get_settings
from core.llm.base import LLMProvider, LLMResponse, Message, StructuredSchema, ToolDefinition
from core.llm.providers import OllamaProvider, OpenRouterProvider
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
        **kwargs: Any,
    ) -> LLMResponse:
        start = time.perf_counter()
        try:
            response = await self.provider.generate(messages, tools=tools, temperature=temperature, **kwargs)
            self._log_request(messages, tools, response, "success", latency_ms=_latency_ms(start))
            return response
        except Exception as exc:
            self._log_request(messages, tools, None, "error", error_message=str(exc), latency_ms=_latency_ms(start))
            raise

    async def generate_structured(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        start = time.perf_counter()
        try:
            response = await self.provider.generate_structured(messages, schema=schema, temperature=temperature, **kwargs)
            self._log_request(messages, None, None, "success", latency_ms=_latency_ms(start), metadata={"structured": True})
            return response
        except Exception as exc:
            self._log_request(messages, None, None, "error", error_message=str(exc), latency_ms=_latency_ms(start), metadata={"structured": True})
            raise

    def generate_sync(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if not hasattr(self.provider, "generate_sync"):
            return asyncio.run(self.generate(messages, tools=tools, temperature=temperature, **kwargs))
        start = time.perf_counter()
        try:
            response = self.provider.generate_sync(messages, tools=tools, temperature=temperature, **kwargs)
            self._log_request(messages, tools, response, "success", latency_ms=_latency_ms(start))
            return response
        except Exception as exc:
            self._log_request(messages, tools, None, "error", error_message=str(exc), latency_ms=_latency_ms(start))
            raise

    def generate_structured_sync(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        if not hasattr(self.provider, "generate_structured_sync"):
            return asyncio.run(self.generate_structured(messages, schema=schema, temperature=temperature, **kwargs))
        start = time.perf_counter()
        try:
            response = self.provider.generate_structured_sync(messages, schema=schema, temperature=temperature, **kwargs)
            self._log_request(messages, None, None, "success", latency_ms=_latency_ms(start), metadata={"structured": True})
            return response
        except Exception as exc:
            self._log_request(messages, None, None, "error", error_message=str(exc), latency_ms=_latency_ms(start), metadata={"structured": True})
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
    ) -> None:
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
            usage=response.usage if response else {},
            prompt_metadata=get_system_prompt_metadata(),
            metadata=metadata or {},
        )


def _latency_ms(start: float) -> int:
    return int(round((time.perf_counter() - start) * 1000))


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


llm_gateway = LLMGateway()
