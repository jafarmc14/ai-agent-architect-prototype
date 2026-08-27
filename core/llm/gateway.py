import asyncio
from typing import Any

from configs import get_settings
from core.llm.base import LLMProvider, LLMResponse, Message, StructuredSchema, ToolDefinition
from core.llm.providers import OllamaProvider, OpenRouterProvider


class LLMGateway:
    """Application-facing LLM gateway that delegates to the configured provider."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or self._build_provider()

    @property
    def provider_name(self) -> str:
        return getattr(self.provider, "provider_name", self.provider.__class__.__name__.lower())

    @property
    def model(self) -> str | None:
        return getattr(self.provider, "model", None)

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
        return await self.provider.generate(messages, tools=tools, temperature=temperature, **kwargs)

    async def generate_structured(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self.provider.generate_structured(messages, schema=schema, temperature=temperature, **kwargs)

    def generate_sync(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if hasattr(self.provider, "generate_sync"):
            return self.provider.generate_sync(messages, tools=tools, temperature=temperature, **kwargs)
        return asyncio.run(self.generate(messages, tools=tools, temperature=temperature, **kwargs))

    def generate_structured_sync(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        if hasattr(self.provider, "generate_structured_sync"):
            return self.provider.generate_structured_sync(messages, schema=schema, temperature=temperature, **kwargs)
        return asyncio.run(self.generate_structured(messages, schema=schema, temperature=temperature, **kwargs))


llm_gateway = LLMGateway()
