from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs import get_settings  # noqa: E402
import core.llm.gateway as gateway_module  # noqa: E402
import core.orchestration.runtime as runtime  # noqa: E402
from core.llm.gateway import LLMGateway  # noqa: E402
from core.llm.provider_catalog import build_provider_options  # noqa: E402
from core.llm.providers import DeepSeekProvider, KimiProvider  # noqa: E402


def test_paid_provider_adapters_use_official_openai_compatible_defaults():
    deepseek = DeepSeekProvider(api_key="test-key")
    kimi = KimiProvider(api_key="test-key")

    assert deepseek.provider_name == "deepseek"
    assert deepseek.model == "deepseek-v4-flash"
    assert deepseek.api_base == "https://api.deepseek.com"
    assert kimi.provider_name == "kimi"
    assert kimi.model == "kimi-k2.6"
    assert kimi.api_base == "https://api.moonshot.ai/v1"


def test_gateway_routes_paid_provider_names_without_business_code_changes():
    original_deepseek = gateway_module.DeepSeekProvider
    original_kimi = gateway_module.KimiProvider
    gateway_module.DeepSeekProvider = lambda model=None: SimpleNamespace(provider_name="deepseek", model=model)
    gateway_module.KimiProvider = lambda model=None: SimpleNamespace(provider_name="kimi", model=model)
    gateway = LLMGateway.__new__(LLMGateway)
    try:
        deepseek = gateway._build_provider("deepseek", "deepseek-v4-pro")
        kimi = gateway._build_provider("kimi", "kimi-k3")
        moonshot_alias = gateway._build_provider("moonshot", "kimi-k2.6")
    finally:
        gateway_module.DeepSeekProvider = original_deepseek
        gateway_module.KimiProvider = original_kimi

    assert (deepseek.provider_name, deepseek.model) == ("deepseek", "deepseek-v4-pro")
    assert (kimi.provider_name, kimi.model) == ("kimi", "kimi-k3")
    assert moonshot_alias.provider_name == "kimi"


def test_external_provider_privacy_scope_includes_paid_providers():
    original_gateway = runtime.llm_gateway
    try:
        for provider_name in ("openrouter", "deepseek", "kimi"):
            runtime.llm_gateway = SimpleNamespace(provider_name=provider_name)
            assert runtime._is_external_llm_provider() is True
        runtime.llm_gateway = SimpleNamespace(provider_name="ollama")
        assert runtime._is_external_llm_provider() is False
    finally:
        runtime.llm_gateway = original_gateway


def test_default_runtime_remains_openrouter_free():
    settings = get_settings()
    assert settings.llm_provider == "openrouter"
    assert settings.openrouter_model == "openrouter/free"


def test_paid_ui_options_are_key_gated():
    base = {
        "deepseek_api_key": "",
        "deepseek_model": "deepseek-v4-flash",
        "kimi_api_key": "",
        "kimi_model": "kimi-k2.6",
    }
    free_options = build_provider_options(SimpleNamespace(**base))
    assert list(free_options) == ["OpenRouter", "Ollama"]

    paid_options = build_provider_options(SimpleNamespace(
        **{**base, "deepseek_api_key": "configured", "kimi_api_key": "configured"}
    ))
    assert paid_options["DeepSeek (Paid)"]["provider"] == "deepseek"
    assert paid_options["Kimi (Paid)"]["provider"] == "kimi"


if __name__ == "__main__":
    test_paid_provider_adapters_use_official_openai_compatible_defaults()
    test_gateway_routes_paid_provider_names_without_business_code_changes()
    test_external_provider_privacy_scope_includes_paid_providers()
    test_default_runtime_remains_openrouter_free()
    test_paid_ui_options_are_key_gated()
    print("Provider integration tests passed.")
