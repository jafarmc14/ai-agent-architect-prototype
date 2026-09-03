from fastapi import Depends, FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware

from configs import get_settings
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConfigureLLMRequest,
    HealthResponse,
    LLMConfigResponse,
    ProviderOptionsResponse,
)
from .services import (
    ChatApplicationService,
    ConfigurationApplicationService,
    chat_application_service,
    configuration_application_service,
)


def get_chat_service() -> ChatApplicationService:
    return chat_application_service


def get_config_service() -> ConfigurationApplicationService:
    return configuration_application_service


def create_app() -> FastAPI:
    app = FastAPI(
        title="Store AI-Agent API",
        version="1.0.0",
        description="FastAPI boundary for the Ubichinon e-commerce AI agent runtime.",
    )
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(settings.api_cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        settings = get_settings()
        return HealthResponse(
            environment=settings.app_env,
            database_provider=settings.database_provider,
        )

    @app.get("/api/v1/config", response_model=LLMConfigResponse)
    def read_llm_config(
        service: ConfigurationApplicationService = Depends(get_config_service),
    ) -> dict:
        return service.llm_config()

    @app.get("/api/v1/providers", response_model=ProviderOptionsResponse)
    def read_provider_options(
        service: ConfigurationApplicationService = Depends(get_config_service),
    ) -> dict:
        return service.provider_options()

    @app.post("/api/v1/config/llm", response_model=LLMConfigResponse)
    def update_llm_config(
        request: ConfigureLLMRequest,
        service: ConfigurationApplicationService = Depends(get_config_service),
    ) -> dict:
        return service.configure_llm(request.provider, request.model)

    @app.post("/api/v1/chat", response_model=ChatResponse)
    def chat(
        request: ChatRequest,
        authorization: str | None = Header(default=None),
        service: ChatApplicationService = Depends(get_chat_service),
    ) -> dict:
        auth_token = request.auth_token or _bearer_token(authorization)
        return service.chat(
            request.message,
            auth_token=auth_token,
            session_id=request.session_id,
        )

    return app


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if value.startswith(prefix):
        return value[len(prefix):].strip()
    return None


def _cors_origins(value: str) -> list[str]:
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


app = create_app()
