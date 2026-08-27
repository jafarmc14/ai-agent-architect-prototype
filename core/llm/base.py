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
