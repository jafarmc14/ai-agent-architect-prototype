from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelGovernance:
    provider: str
    model: str
    model_version: str
    pinned: bool
    alias: bool
    source: str

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "pinned": self.pinned,
            "alias": self.alias,
            "source": self.source,
        }


def build_model_governance(provider: str, model: str, configured_version: str = "") -> ModelGovernance:
    provider = provider.strip().lower()
    model = model.strip()
    configured_version = configured_version.strip()
    if configured_version:
        return ModelGovernance(
            provider=provider,
            model=model,
            model_version=configured_version,
            pinned=True,
            alias=False,
            source="configured_model_version",
        )

    inferred_alias = _looks_like_alias(provider, model)
    return ModelGovernance(
        provider=provider,
        model=model,
        model_version=f"alias:{model}",
        pinned=False,
        alias=inferred_alias,
        source="model_alias_observed",
    )


def _looks_like_alias(provider: str, model: str) -> bool:
    lowered = model.lower()
    if provider == "openrouter":
        return lowered in {"openrouter/free"} or ":free" in lowered or lowered.endswith("/free")
    if provider == "ollama":
        return "@" not in lowered and "sha256:" not in lowered
    return True
