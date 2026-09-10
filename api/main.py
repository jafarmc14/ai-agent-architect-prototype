from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

from configs import get_settings
from .schemas import (
    ChatRequest,
    FeedbackRequest,
    QualityReviewRequest,
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
from core.auth.jwt import AuthError, create_session_token, verify_session_token
from core.auth.login_throttle import login_throttle
from core.auth.password import hash_password, verify_password
from core.repositories.user_repository import UserRepository
from core.repositories.pilot_repository import PilotRepository
from core.services.pilot_access import require_pilot_access
from uuid import UUID
from configs.experimentation import experiment_settings
from core.repositories.production_monitoring_repository import ProductionMonitoringRepository
from core.services.production_metrics import monitoring_report, promotion_gate

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
    experiment_settings()
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
        authorization: str | None = Header(default=None),
        service: ConfigurationApplicationService = Depends(get_config_service),
    ) -> dict:
        _require_authorized(authorization)
        _pilot_guard(_bearer_token(authorization))
        if get_settings().pilot_enabled:
            claims = verify_session_token(_bearer_token(authorization))
            if claims.get("role") not in {"admin", "manager"}:
                raise HTTPException(403, "Runtime configuration is restricted during the pilot.")
        return service.configure_llm(request.provider, request.model)

    @app.post("/api/v1/chat", response_model=ChatResponse)
    def chat(
        request: ChatRequest,
        authorization: str | None = Header(default=None),
        service: ChatApplicationService = Depends(get_chat_service),
    ) -> dict:
        auth_token = request.auth_token or _bearer_token(authorization)
        _pilot_guard(auth_token)
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
        ip = _client_ip(http_request)

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
        _pilot_guard(token)
        return {
            "token": token,
            "user": LoginUser(
                id=str(user["id"]),
                name=user.get("name") or "",
                email=user.get("email") or "",
                role=role,
            ),
        }

    @app.post("/api/v1/feedback")
    def submit_feedback(request: FeedbackRequest, authorization: str | None = Header(default=None)) -> dict:
        claims = _feedback_identity(authorization)
        try:
            return PilotRepository().feedback(str(request.request_id), claims.get("tenant_id", "default"), claims["sub"], request.kind)
        except LookupError as exc:
            raise HTTPException(404, "Request not found.") from exc

    @app.get("/api/v1/pilot/usage")
    def pilot_usage(days: int = Query(default=7, ge=1, le=90), authorization: str | None = Header(default=None)) -> dict:
        claims = _feedback_identity(authorization)
        if claims.get("role") not in {"manager", "admin"}:
            raise HTTPException(403, "Pilot reports require a manager or admin role.")
        return PilotRepository().usage(claims.get("tenant_id", "default"), days)

    @app.get("/api/v1/monitoring/quality")
    def production_quality(days: int = Query(default=7, ge=1, le=90), authorization: str | None = Header(default=None)):
        claims = _monitoring_identity(authorization)
        return monitoring_report(*ProductionMonitoringRepository().rows(claims.get("tenant_id", "default"), days))

    @app.post("/api/v1/monitoring/reviews/{request_id}")
    def quality_review(request_id: UUID, review: QualityReviewRequest, authorization: str | None = Header(default=None)):
        claims = _monitoring_identity(authorization)
        saved = ProductionMonitoringRepository().review(str(request_id), claims.get("tenant_id", "default"), claims["sub"], review.model_dump())
        if not saved:
            raise HTTPException(404, "Request not found.")
        return {"status": "saved"}

    @app.get("/api/v1/monitoring/experiments/{experiment_id}")
    def experiment_report(experiment_id: str, days: int = Query(default=7, ge=1, le=90), authorization: str | None = Header(default=None)):
        claims = _monitoring_identity(authorization)
        _, rows = ProductionMonitoringRepository().rows(claims.get("tenant_id", "default"), days)
        return promotion_gate(rows, experiment_id)

    return app


def _monitoring_identity(authorization):
    claims = _feedback_identity(authorization)
    if claims.get("role") not in {"manager", "admin"}:
        raise HTTPException(403, "Monitoring requires a manager or admin role.")
    return claims


def _pilot_guard(token: str | None) -> None:
    try:
        require_pilot_access(token)
    except (AuthError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Invalid or expired session token.") from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _feedback_identity(authorization: str | None) -> dict:
    _require_authorized(authorization)
    token = _bearer_token(authorization)
    _pilot_guard(token)
    if get_settings().database_provider != "postgres":
        raise HTTPException(503, "Feedback and pilot reports require PostgreSQL.")
    return verify_session_token(token)


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if value.startswith(prefix):
        return value[len(prefix):].strip()
    return None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _require_authorized(authorization: str | None) -> None:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    try:
        verify_session_token(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        ) from exc


def _cors_origins(value: str) -> list[str]:
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


app = create_app()
