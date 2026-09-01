from typing import Any

from langchain_openai import ChatOpenAI

from configs import get_settings
from core.llm.base import LLMProvider, LLMResponse, LLMToolCall, Message, StructuredSchema, ToolDefinition, extract_llm_usage
from core.llm.model_governance import build_model_governance


DEFAULT_OLLAMA_MODEL = "llama3.1"
DEFAULT_OLLAMA_API_BASE = "http://localhost:11434/v1"


class OllamaProvider(LLMProvider):
    """Ollama adapter backed by Ollama's OpenAI-compatible local API."""

    provider_name = "ollama"
    supports_prompt_caching = False

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.7,
    ):
        settings = get_settings()
        self.model = model or settings.ollama_model or DEFAULT_OLLAMA_MODEL
        self.api_base = api_base or settings.ollama_api_base or DEFAULT_OLLAMA_API_BASE
        self.api_key = api_key or settings.ollama_api_key
        self.temperature = temperature
        self.request_timeout = settings.max_agent_runtime_seconds
        self.model_governance = build_model_governance(
            provider=self.provider_name,
            model=self.model,
            configured_version=settings.ollama_model_version,
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
