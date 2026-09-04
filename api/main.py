from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from configs import get_settings
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConfigureLLMRequest,
    HealthResponse,
    LLMConfigResponse,
    LoginRequest,
    LoginResponse,
    LoginUser,
    ProviderOptionsResponse,
)
from .services import (
    ChatApplicationService,
    ConfigurationApplicationService,
    chat_application_service,
    configuration_application_service,
)
from core.auth.jwt import create_session_token
from core.auth.login_throttle import login_throttle
from core.auth.password import hash_password, verify_password
from core.repositories.user_repository import UserRepository

_DUMMY_PASSWORD_HASH = hash_password("login-timing-equalizer")
_user_repository = UserRepository()


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

    @app.post("/api/v1/auth/login", response_model=LoginResponse)
    def login(
        request: LoginRequest,
        http_request: Request,
    ) -> dict:
        settings = get_settings()
        if settings.database_provider != "postgres":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Login requires a PostgreSQL database.",
            )
        username = request.username.strip().lower()
        ip = http_request.client.host if http_request.client else "unknown"

        retry_after = login_throttle.check(username, ip)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        user = _user_repository.find_login_user(username)
        if user is None:
            verify_password(request.password, _DUMMY_PASSWORD_HASH)
            login_throttle.record_failure(username, ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )
        if not verify_password(request.password, user.get("password_hash")):
            login_throttle.record_failure(username, ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )

        login_throttle.record_success(username)
        metadata = user.get("metadata") or {}
        role = metadata.get("role", "customer")
        tenant_id = metadata.get("tenant_id", "default")
        token = create_session_token(
            user_id=str(user["id"]),
            email=user.get("email") or "",
            name=user.get("name") or "",
            role=role,
            tenant_id=tenant_id,
        )
        return {
            "token": token,
            "user": LoginUser(
                id=str(user["id"]),
                name=user.get("name") or "",
                email=user.get("email") or "",
                role=role,
            ),
        }

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
