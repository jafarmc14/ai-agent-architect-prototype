import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_ENVIRONMENTS = {"development", "testing", "staging", "production"}
SUPPORTED_DATABASE_PROVIDERS = {"sqlite", "postgres"}


def _load_environment_files() -> str:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in SUPPORTED_ENVIRONMENTS:
        supported = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise ValueError(f"Unsupported APP_ENV {app_env!r}. Supported values: {supported}.")

    load_dotenv(PROJECT_ROOT / f".env.{app_env}", override=True)
    load_dotenv(PROJECT_ROOT / ".env.secrets", override=True)
    load_dotenv(PROJECT_ROOT / f".env.{app_env}.secrets", override=True)
    return app_env


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default

    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


@dataclass(frozen=True)
class AppSettings:
    app_env: str
    debug: bool
    database_provider: str
    database_path: Path
    database_password: str
    postgres_database_url: str
    knowledge_base_path: Path
    knowledge_base_dir: Path
    embedding_model: str
    embedding_api_base: str
    embedding_api_key: str
    vector_dimension: int
    jwt_secret: str
    llm_provider: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_model_version: str
    openrouter_api_base: str
    ollama_api_key: str
    ollama_model: str
    ollama_model_version: str
    ollama_api_base: str
    deepseek_api_key: str
    deepseek_model: str
    deepseek_model_version: str
    deepseek_api_base: str
    kimi_api_key: str
    kimi_model: str
    kimi_model_version: str
    kimi_api_base: str
    model_routing_enabled: bool
    routing_cheap_provider: str
    routing_cheap_model: str
    routing_standard_provider: str
    routing_standard_model: str
    routing_premium_provider: str
    routing_premium_model: str
    routing_cheap_tasks: str
    routing_standard_tasks: str
    routing_premium_tasks: str
    routing_confidence_threshold: float
    routing_evidence_threshold: float
    provider_fallback_enabled: bool
    provider_fallback_chain: str
    provider_fallback_max_attempts: int
    provider_fallback_backoff_seconds: float
    circuit_breaker_enabled: bool
    circuit_breaker_failure_threshold: int
    circuit_breaker_cooldown_seconds: float
    high_risk_write_actions_enabled: bool
    max_input_tokens: int
    max_output_tokens: int
    max_tool_calls: int
    max_agent_steps: int
    max_agent_runtime_seconds: int
    max_request_cost_usd: float
    max_input_price_per_million: float
    max_output_price_per_million: float
    user_rate_limit_requests: int
    user_rate_limit_window_seconds: int
    tenant_daily_request_quota: int
    tenant_daily_token_quota: int
    tenant_daily_cost_quota_usd: float
    expensive_repeat_limit: int
    expensive_repeat_window_seconds: int
    max_identical_tool_calls: int
    max_low_progress_steps: int
    max_planning_cycle_length: int


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    app_env = _load_environment_files()
    benchmark_mode = os.getenv("PROVIDER_BENCHMARK_MODE", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }
    database_provider = (
        os.getenv("BENCHMARK_DATABASE_PROVIDER", "sqlite")
        if benchmark_mode
        else os.getenv("DATABASE_PROVIDER", "sqlite")
    ).strip().lower()
    if database_provider not in SUPPORTED_DATABASE_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_DATABASE_PROVIDERS))
        raise ValueError(f"Unsupported DATABASE_PROVIDER {database_provider!r}. Supported values: {supported}.")

    return AppSettings(
        app_env=app_env,
        debug=os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"},
        database_provider=database_provider,
        database_path=_path_from_env(
            "BENCHMARK_DATABASE_PATH" if benchmark_mode else "DATABASE_PATH",
            PROJECT_ROOT / "toko.db",
        ),
        database_password=os.getenv("DB_PASSWORD", ""),
        postgres_database_url=os.getenv("DATABASE_URL", ""),
        knowledge_base_path=_path_from_env("KNOWLEDGE_BASE_PATH", PROJECT_ROOT / "knowledge_base.txt"),
        knowledge_base_dir=_path_from_env("KNOWLEDGE_BASE_DIR", PROJECT_ROOT / "knowledge_base"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        embedding_api_base=os.getenv("EMBEDDING_API_BASE", "http://localhost:11434/v1"),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", "ollama"),
        vector_dimension=int(os.getenv("VECTOR_DIMENSION", "768")),
        jwt_secret=os.getenv("JWT_SECRET", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "openrouter").strip().lower(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "dummy"),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        openrouter_model_version=os.getenv("OPENROUTER_MODEL_VERSION", "").strip(),
        openrouter_api_base=os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
        ollama_api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        ollama_model_version=os.getenv("OLLAMA_MODEL_VERSION", "").strip(),
        ollama_api_base=os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        deepseek_model_version=os.getenv("DEEPSEEK_MODEL_VERSION", "").strip(),
        deepseek_api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        kimi_api_key=os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY", ""),
        kimi_model=os.getenv("KIMI_MODEL", "kimi-k2.6"),
        kimi_model_version=os.getenv("KIMI_MODEL_VERSION", "").strip(),
        kimi_api_base=os.getenv("KIMI_API_BASE", "https://api.moonshot.ai/v1"),
        model_routing_enabled=os.getenv("MODEL_ROUTING_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"},
        routing_cheap_provider=os.getenv("ROUTING_CHEAP_PROVIDER", "openrouter").strip().lower(),
        routing_cheap_model=os.getenv("ROUTING_CHEAP_MODEL", "openrouter/free").strip(),
        routing_standard_provider=os.getenv("ROUTING_STANDARD_PROVIDER", "deepseek").strip().lower(),
        routing_standard_model=os.getenv("ROUTING_STANDARD_MODEL", "deepseek-v4-flash").strip(),
        routing_premium_provider=os.getenv("ROUTING_PREMIUM_PROVIDER", "kimi").strip().lower(),
        routing_premium_model=os.getenv("ROUTING_PREMIUM_MODEL", "kimi-k2.6").strip(),
        routing_cheap_tasks=os.getenv(
            "ROUTING_CHEAP_TASKS", "intent,extraction,product_search,orders,cart,escalation"
        ),
        routing_standard_tasks=os.getenv("ROUTING_STANDARD_TASKS", "simple_rag"),
        routing_premium_tasks=os.getenv("ROUTING_PREMIUM_TASKS", "complex_rag,agentic_workflow"),
        routing_confidence_threshold=float(os.getenv("ROUTING_CONFIDENCE_THRESHOLD", "0.70")),
        routing_evidence_threshold=float(os.getenv("ROUTING_EVIDENCE_THRESHOLD", "0.65")),
        provider_fallback_enabled=os.getenv("PROVIDER_FALLBACK_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"},
        provider_fallback_chain=os.getenv(
            "PROVIDER_FALLBACK_CHAIN", "deepseek,kimi,openrouter,ollama"
        ),
        provider_fallback_max_attempts=max(1, int(os.getenv("PROVIDER_FALLBACK_MAX_ATTEMPTS", "3"))),
        provider_fallback_backoff_seconds=max(
            0.0, float(os.getenv("PROVIDER_FALLBACK_BACKOFF_SECONDS", "0.25"))
        ),
        circuit_breaker_enabled=os.getenv("CIRCUIT_BREAKER_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"},
        circuit_breaker_failure_threshold=max(
            1, int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3"))
        ),
        circuit_breaker_cooldown_seconds=max(
            0.0, float(os.getenv("CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60"))
        ),
        high_risk_write_actions_enabled=os.getenv("HIGH_RISK_WRITE_ACTIONS_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"},
        max_input_tokens=int(os.getenv("MAX_INPUT_TOKENS", "2000")),
        max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "1200")),
        max_tool_calls=int(os.getenv("MAX_TOOL_CALLS", "6")),
        max_agent_steps=int(os.getenv("MAX_AGENT_STEPS", "4")),
        max_agent_runtime_seconds=int(os.getenv("MAX_AGENT_RUNTIME_SECONDS", "60")),
        max_request_cost_usd=float(os.getenv("MAX_REQUEST_COST_USD", "0.05")),
        max_input_price_per_million=float(os.getenv("MAX_INPUT_PRICE_PER_MILLION", "0")),
        max_output_price_per_million=float(os.getenv("MAX_OUTPUT_PRICE_PER_MILLION", "0")),
        user_rate_limit_requests=int(os.getenv("USER_RATE_LIMIT_REQUESTS", "20")),
        user_rate_limit_window_seconds=int(os.getenv("USER_RATE_LIMIT_WINDOW_SECONDS", "60")),
        tenant_daily_request_quota=int(os.getenv("TENANT_DAILY_REQUEST_QUOTA", "1000")),
        tenant_daily_token_quota=int(os.getenv("TENANT_DAILY_TOKEN_QUOTA", "1000000")),
        tenant_daily_cost_quota_usd=float(os.getenv("TENANT_DAILY_COST_QUOTA_USD", "10")),
        expensive_repeat_limit=int(os.getenv("EXPENSIVE_REPEAT_LIMIT", "3")),
        expensive_repeat_window_seconds=int(os.getenv("EXPENSIVE_REPEAT_WINDOW_SECONDS", "300")),
        max_identical_tool_calls=int(os.getenv("MAX_IDENTICAL_TOOL_CALLS", "1")),
        max_low_progress_steps=int(os.getenv("MAX_LOW_PROGRESS_STEPS", "2")),
        max_planning_cycle_length=int(os.getenv("MAX_PLANNING_CYCLE_LENGTH", "3")),
    )


def reload_settings() -> AppSettings:
    get_settings.cache_clear()
    return get_settings()
