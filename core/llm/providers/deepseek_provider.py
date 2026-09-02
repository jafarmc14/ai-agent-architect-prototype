from configs import get_settings

from .openai_compatible_provider import OpenAICompatibleProvider


DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"


class DeepSeekProvider(OpenAICompatibleProvider):
    """Production DeepSeek adapter using the OpenAI-compatible API."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.7,
    ):
        settings = get_settings()
        super().__init__(
            provider_name="deepseek",
            model=model or settings.deepseek_model or DEFAULT_DEEPSEEK_MODEL,
            api_key=api_key or settings.deepseek_api_key,
            api_base=api_base or settings.deepseek_api_base or DEFAULT_DEEPSEEK_API_BASE,
            model_version=settings.deepseek_model_version,
            temperature=temperature,
            request_timeout=settings.max_agent_runtime_seconds,
        )
