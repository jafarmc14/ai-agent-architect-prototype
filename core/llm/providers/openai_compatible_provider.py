from typing import Any

from langchain_openai import ChatOpenAI

from core.llm.base import (
    LLMProvider,
    LLMResponse,
    LLMToolCall,
    Message,
    StructuredSchema,
    ToolDefinition,
    extract_llm_usage,
)
from core.llm.model_governance import build_model_governance


class OpenAICompatibleProvider(LLMProvider):
    """Shared adapter for hosted providers implementing OpenAI Chat Completions."""

    supports_prompt_caching = False

    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        api_key: str,
        api_base: str,
        model_version: str = "",
        temperature: float = 0.7,
        request_timeout: int = 60,
    ):
        if not api_key:
            variable = "DEEPSEEK_API_KEY" if provider_name == "deepseek" else "MOONSHOT_API_KEY"
            raise ValueError(f"{variable} is required when LLM_PROVIDER={provider_name}.")
        self.provider_name = provider_name
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self.temperature = temperature
        self.request_timeout = request_timeout
        self.model_governance = build_model_governance(
            provider=provider_name,
            model=model,
            configured_version=model_version,
        )
        self.model_version = self.model_governance.model_version
        self.client = self._build_client(temperature)

    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        raw_response = await self._client_for_call(tools, temperature).ainvoke(messages, **kwargs)
        return self._to_response(raw_response)

    async def generate_structured(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        client = self._client_for_call(temperature=temperature).with_structured_output(schema)
        return await client.ainvoke(messages, **kwargs)

    def generate_sync(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        raw_response = self._client_for_call(tools, temperature).invoke(messages, **kwargs)
        return self._to_response(raw_response)

    def generate_structured_sync(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        client = self._client_for_call(temperature=temperature).with_structured_output(schema)
        return client.invoke(messages, **kwargs)

    def _build_client(self, temperature: float):
        return ChatOpenAI(
            openai_api_base=self.api_base,
            openai_api_key=self.api_key,
            model_name=self.model,
            temperature=temperature,
            timeout=self.request_timeout,
        )

    def _client_for_call(
        self,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
    ):
        client = self.client
        if temperature is not None and temperature != self.temperature:
            client = self._build_client(temperature)
        if tools:
            return client.bind_tools(tools)
        return client

    def _to_response(self, raw_response: Any) -> LLMResponse:
        return LLMResponse(
            text=getattr(raw_response, "content", "") or "",
            tool_calls=[
                LLMToolCall(
                    id=tool_call.get("id", ""),
                    name=tool_call.get("name", ""),
                    arguments=tool_call.get("args", {}),
                    raw=tool_call,
                )
                for tool_call in getattr(raw_response, "tool_calls", []) or []
            ],
            raw=raw_response,
            usage=extract_llm_usage(raw_response),
            model=self.model,
            model_version=self.model_version,
            model_metadata=self.model_governance.metadata(),
        )
