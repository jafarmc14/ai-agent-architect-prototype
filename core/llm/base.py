from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


Message = dict[str, Any]
ToolDefinition = Any
StructuredSchema = dict[str, Any] | type[Any]


@dataclass
class LLMToolCall:
    """Provider-neutral representation of an LLM tool call."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw: Any = None


@dataclass
class LLMResponse:
    """Provider-neutral LLM response object."""

    text: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    raw: Any = None
    usage: dict[str, Any] | None = None
    model: str | None = None
    model_version: str | None = None
    model_metadata: dict[str, Any] | None = None


class LLMProvider(ABC):
    """Base interface for all LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a natural-language response, optionally with tool calls."""

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[Message],
        schema: StructuredSchema,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Generate output that conforms to the provided structured schema."""


def extract_llm_usage(raw_response: Any) -> dict[str, Any]:
    """Normalize token and provider-cost metadata from LangChain responses."""
    usage: dict[str, Any] = {}
    sources = [getattr(raw_response, "usage_metadata", None)]
    response_metadata = getattr(raw_response, "response_metadata", None) or {}
    if isinstance(response_metadata, dict):
        sources.extend([
            response_metadata.get("token_usage"),
            response_metadata.get("usage"),
        ])
        for key in ("cost", "cost_usd", "total_cost"):
            if response_metadata.get(key) is not None:
                usage["cost_usd"] = response_metadata[key]

    for source in sources:
        if not source:
            continue
        if hasattr(source, "model_dump"):
            source = source.model_dump()
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if value is not None:
                usage[key] = value

    aliases = {
        "prompt_tokens": "input_tokens",
        "completion_tokens": "output_tokens",
    }
    for source_key, target_key in aliases.items():
        if target_key not in usage and source_key in usage:
            usage[target_key] = usage[source_key]
    if "total_tokens" not in usage:
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if input_tokens is not None and output_tokens is not None:
            usage["total_tokens"] = int(input_tokens) + int(output_tokens)
    return usage
