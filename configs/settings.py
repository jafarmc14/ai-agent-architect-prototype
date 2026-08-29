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
    openrouter_api_base: str
    ollama_api_key: str
    ollama_model: str
    ollama_api_base: str


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    app_env = _load_environment_files()
    database_provider = os.getenv("DATABASE_PROVIDER", "sqlite").strip().lower()
    if database_provider not in SUPPORTED_DATABASE_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_DATABASE_PROVIDERS))
        raise ValueError(f"Unsupported DATABASE_PROVIDER {database_provider!r}. Supported values: {supported}.")

    return AppSettings(
        app_env=app_env,
        debug=os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"},
        database_provider=database_provider,
        database_path=_path_from_env("DATABASE_PATH", PROJECT_ROOT / "toko.db"),
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
        openrouter_api_base=os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
        ollama_api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        ollama_api_base=os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1"),
    )


def reload_settings() -> AppSettings:
    get_settings.cache_clear()
    return get_settings()
