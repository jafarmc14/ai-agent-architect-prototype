from typing import Any

from agent import configure_llm_provider, get_agent_response_with_trace, get_llm_config
from core.llm.provider_catalog import build_provider_options
from core.optimization import summarize_token_trace


class ChatApplicationService:
    """Small API-facing adapter over the existing orchestration runtime."""

    def chat(self, message: str, *, auth_token: str | None, session_id: str) -> dict[str, Any]:
        trace = get_agent_response_with_trace(
            message,
            auth_token=auth_token,
            session_id=session_id,
        )
        trace["token_usage"] = summarize_token_trace(trace)
        return trace


class ConfigurationApplicationService:
    def llm_config(self) -> dict[str, Any]:
        return get_llm_config()

    def provider_options(self) -> dict[str, Any]:
        return {"options": build_provider_options()}

    def configure_llm(self, provider: str, model: str | None = None) -> dict[str, Any]:
        return configure_llm_provider(provider, model)


chat_application_service = ChatApplicationService()
configuration_application_service = ConfigurationApplicationService()
