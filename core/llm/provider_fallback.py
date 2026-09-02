import re
from dataclasses import asdict, dataclass
from typing import Any

from core.llm.base import LLMResponse


@dataclass(frozen=True)
class FallbackTarget:
    provider: str
    model: str


@dataclass(frozen=True)
class FailureClassification:
    category: str
    retryable: bool
    status_code: int | None = None

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


class InvalidProviderResponse(RuntimeError):
    """Provider returned successfully but without a usable response payload."""


class ProviderFallbackExhausted(RuntimeError):
    def __init__(self, original_error: Exception, attempts: list[dict[str, Any]]):
        super().__init__(str(original_error))
        self.original_error = original_error
        self.attempts = attempts


class ProviderFallbackPolicy:
    """Builds an available fallback chain and classifies transient provider failures."""

    def __init__(self, settings: Any):
        self.settings = settings

    def targets(self, primary_provider: str, primary_model: str) -> list[FallbackTarget]:
        primary = FallbackTarget(primary_provider.strip().lower(), primary_model)
        if not self.settings.provider_fallback_enabled:
            return [primary]

        targets = [primary]
        for provider in _csv(self.settings.provider_fallback_chain):
            normalized = "kimi" if provider == "moonshot" else provider
            target = FallbackTarget(normalized, self._model_for(normalized))
            if not target.model or not self._provider_available(normalized):
                continue
            if (target.provider, target.model) not in {(item.provider, item.model) for item in targets}:
                targets.append(target)
        return targets[:max(1, self.settings.provider_fallback_max_attempts)]

    def classify(self, error: Exception) -> FailureClassification:
        if isinstance(error, InvalidProviderResponse):
            return FailureClassification("invalid_response", True)

        status_code = _status_code(error)
        if status_code == 429:
            return FailureClassification("rate_limit", True, status_code)
        if status_code is not None and 500 <= status_code <= 599:
            return FailureClassification("provider_server_error", True, status_code)
        if status_code is not None:
            return FailureClassification("non_retryable_http_error", False, status_code)

        name = error.__class__.__name__.lower()
        message = str(error).lower()
        if isinstance(error, TimeoutError) or "timeout" in name or "timed out" in message:
            return FailureClassification("timeout", True)
        if isinstance(error, ConnectionError) or any(marker in name or marker in message for marker in (
            "connectionerror", "connecterror", "connection failure", "connection refused",
            "connection reset", "network is unreachable", "name resolution",
        )):
            return FailureClassification("connection_failure", True)
        if re.search(r"(?:status|error|code)\D*429\b", message):
            return FailureClassification("rate_limit", True, 429)
        match = re.search(r"(?:status|error|code)\D*(5\d\d)\b", message)
        if match:
            return FailureClassification("provider_server_error", True, int(match.group(1)))
        return FailureClassification("non_retryable_error", False)

    def _model_for(self, provider: str) -> str:
        return {
            "openrouter": self.settings.openrouter_model,
            "ollama": self.settings.ollama_model,
            "deepseek": self.settings.deepseek_model,
            "kimi": self.settings.kimi_model,
        }.get(provider, "")

    def _provider_available(self, provider: str) -> bool:
        if provider == "ollama":
            return True
        if provider == "openrouter":
            return bool(self.settings.openrouter_api_key and self.settings.openrouter_api_key != "dummy")
        if provider == "deepseek":
            return bool(self.settings.deepseek_api_key)
        if provider == "kimi":
            return bool(self.settings.kimi_api_key)
        return False


def validate_provider_response(response: Any, *, structured: bool = False) -> None:
    if response is None:
        raise InvalidProviderResponse("Provider returned no response.")
    if structured:
        if isinstance(response, str) and not response.strip():
            raise InvalidProviderResponse("Provider returned an empty structured response.")
        return
    if not isinstance(response, LLMResponse):
        raise InvalidProviderResponse("Provider returned an unexpected response type.")
    if not str(response.text or "").strip() and not response.tool_calls:
        raise InvalidProviderResponse("Provider returned neither text nor tool calls.")


def _status_code(error: Exception) -> int | None:
    candidates = [
        getattr(error, "status_code", None),
        getattr(error, "code", None),
        getattr(getattr(error, "response", None), "status_code", None),
    ]
    for value in candidates:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if 100 <= parsed <= 599:
            return parsed
    return None


def _csv(value: str) -> list[str]:
    return [item.strip().lower() for item in (value or "").split(",") if item.strip()]
