from typing import Any

from configs import get_settings


def build_provider_options(settings=None) -> dict[str, dict[str, Any]]:
    """Return UI-safe providers, gating paid providers on configured credentials."""
    settings = settings or get_settings()
    options = {
        "OpenRouter": {
            "provider": "openrouter",
            "models": ["openrouter/free"],
        },
        "Ollama": {
            "provider": "ollama",
            "models": ["llama3.1", "qwen2.5", "mistral"],
        },
    }
    if settings.deepseek_api_key:
        options["DeepSeek (Paid)"] = {
            "provider": "deepseek",
            "models": _unique([settings.deepseek_model, "deepseek-v4-flash", "deepseek-v4-pro"]),
        }
    if settings.kimi_api_key:
        options["Kimi (Paid)"] = {
            "provider": "kimi",
            "models": _unique([settings.kimi_model, "kimi-k2.6", "kimi-k3"]),
        }
    return options


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
