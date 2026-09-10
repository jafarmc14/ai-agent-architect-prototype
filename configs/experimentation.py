import os
from dataclasses import dataclass

from configs import get_settings


@dataclass(frozen=True)
class ExperimentSettings:
    mode: str
    experiment_id: str
    provider: str
    model: str
    tenants: tuple[str, ...]
    percentage: float
    daily_jobs: int
    timeout: float
    max_input_tokens: int
    max_output_tokens: int


def experiment_settings() -> ExperimentSettings:
    get_settings()
    mode = os.getenv("EXPERIMENT_MODE", "off").strip().lower()
    if mode not in {"off", "shadow", "ab"}:
        raise ValueError("EXPERIMENT_MODE must be off, shadow, or ab.")
    result = ExperimentSettings(
        mode, os.getenv("EXPERIMENT_ID", ""),
        os.getenv("EXPERIMENT_CANDIDATE_PROVIDER", "ollama"),
        os.getenv("EXPERIMENT_CANDIDATE_MODEL", ""),
        tuple(x.strip() for x in os.getenv("EXPERIMENT_TENANTS", "").split(",") if x.strip()),
        float(os.getenv("EXPERIMENT_PERCENTAGE", "10")),
        int(os.getenv("SHADOW_DAILY_JOBS", "20")),
        float(os.getenv("SHADOW_TIMEOUT_SECONDS", "30")),
        int(os.getenv("SHADOW_MAX_INPUT_TOKENS", "3000")),
        int(os.getenv("SHADOW_MAX_OUTPUT_TOKENS", "500")),
    )
    if not 0 <= result.percentage <= 10 or not 1 <= result.daily_jobs <= 1000:
        raise ValueError("Candidate traffic must be 0-10%; shadow daily jobs must be 1-1000.")
    if not 1 <= result.timeout <= 120 or not 1 <= result.max_input_tokens <= 8000 or not 1 <= result.max_output_tokens <= 2000:
        raise ValueError("Invalid shadow resource limits.")
    if mode != "off" and (not result.experiment_id or not result.model or not result.tenants):
        raise ValueError("An experiment requires ID, candidate model, and explicit tenant allowlist.")
    if mode != "off" and result.provider not in {"ollama", "openrouter", "deepseek", "kimi"}:
        raise ValueError("Unsupported candidate provider.")
    return result
