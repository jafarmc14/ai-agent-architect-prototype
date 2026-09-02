from configs import get_settings

from .openai_compatible_provider import OpenAICompatibleProvider


DEFAULT_KIMI_MODEL = "kimi-k2.6"
DEFAULT_KIMI_API_BASE = "https://api.moonshot.ai/v1"


class KimiProvider(OpenAICompatibleProvider):
    """Production Kimi/Moonshot adapter using the OpenAI-compatible API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.7,
    ):
        settings = get_settings()
        super().__init__(
            provider_name="kimi",
            model=model or settings.kimi_model or DEFAULT_KIMI_MODEL,
            api_key=api_key or settings.kimi_api_key,
            api_base=api_base or settings.kimi_api_base or DEFAULT_KIMI_API_BASE,
            model_version=settings.kimi_model_version,
            temperature=temperature,
            request_timeout=settings.max_agent_runtime_seconds,
        )
