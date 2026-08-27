import os
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from core.llm.base import LLMProvider, LLMResponse, LLMToolCall, Message, StructuredSchema, ToolDefinition


load_dotenv()

DEFAULT_OPENROUTER_MODEL = "openrouter/free"
DEFAULT_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(LLMProvider):
    """OpenRouter adapter backed by LangChain's ChatOpenAI client."""

    provider_name = "openrouter"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str = DEFAULT_OPENROUTER_API_BASE,
        temperature: float = 0.7,
    ):
        self.model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        self.api_base = api_base
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "dummy")
        self.temperature = temperature
        self.client = self._build_client(temperature)

    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._client_for_call(tools=tools, temperature=temperature)
        raw_response = await client.ainvoke(messages, **kwargs)
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
        client = self._client_for_call(tools=tools, temperature=temperature)
        raw_response = client.invoke(messages, **kwargs)
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
            usage=getattr(raw_response, "usage_metadata", None),
            model=self.model,
        )
