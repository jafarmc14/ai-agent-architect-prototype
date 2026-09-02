from dataclasses import asdict, dataclass
from typing import Any


COMPLEXITY_LEVELS = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class RoutingTarget:
    tier: str
    provider: str
    model: str
    available: bool = True


@dataclass(frozen=True)
class RoutingDecision:
    enabled: bool
    task: str
    complexity: str
    confidence: float | None
    evidence_score: float | None
    requested_tier: str
    selected_tier: str
    provider: str
    model: str
    cheap_first: bool
    premium_model_used: bool
    fallback_used: bool
    reasons: tuple[str, ...]

    def metadata(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


class ModelRouter:
    """Deterministic model policy; it never calls an LLM to choose an LLM."""

    def __init__(self, settings: Any):
        self.settings = settings
        self.targets = {
            "cheap": RoutingTarget(
                "cheap", settings.routing_cheap_provider, settings.routing_cheap_model,
                self._provider_available(settings.routing_cheap_provider),
            ),
            "standard": RoutingTarget(
                "standard", settings.routing_standard_provider, settings.routing_standard_model,
                self._provider_available(settings.routing_standard_provider),
            ),
            "premium": RoutingTarget(
                "premium", settings.routing_premium_provider, settings.routing_premium_model,
                self._provider_available(settings.routing_premium_provider),
            ),
        }

    def decide(
        self,
        *,
        task: str,
        base_provider: str,
        base_model: str,
        estimated_input_tokens: int = 0,
        input_budget: int = 1,
        tool_count: int = 0,
        route_context: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        context = route_context or {}
        confidence = _score(context.get("confidence"))
        evidence_score = _score(context.get("evidence_score"))
        complexity = self._complexity(
            task=task,
            explicit=context.get("complexity"),
            estimated_input_tokens=estimated_input_tokens,
            input_budget=input_budget,
            tool_count=tool_count,
        )
        if not self.settings.model_routing_enabled:
            return RoutingDecision(
                enabled=False,
                task=task,
                complexity=complexity,
                confidence=confidence,
                evidence_score=evidence_score,
                requested_tier="configured",
                selected_tier="configured",
                provider=base_provider,
                model=base_model,
                cheap_first=False,
                premium_model_used=False,
                fallback_used=False,
                reasons=("routing_disabled",),
            )

        requested_tier, reasons = self._requested_tier(
            task=task,
            complexity=complexity,
            confidence=confidence,
            evidence_score=evidence_score,
        )
        target, fallback_used = self._available_target(
            requested_tier,
            RoutingTarget("configured", base_provider, base_model, True),
        )
        if fallback_used:
            reasons.append(f"{requested_tier}_tier_unavailable")
        return RoutingDecision(
            enabled=True,
            task=task,
            complexity=complexity,
            confidence=confidence,
            evidence_score=evidence_score,
            requested_tier=requested_tier,
            selected_tier=target.tier,
            provider=target.provider,
            model=target.model,
            cheap_first=requested_tier == "cheap",
            premium_model_used=target.tier == "premium",
            fallback_used=fallback_used,
            reasons=tuple(reasons),
        )

    def _requested_tier(
        self,
        *,
        task: str,
        complexity: str,
        confidence: float | None,
        evidence_score: float | None,
    ) -> tuple[str, list[str]]:
        reasons = [f"task:{task}", f"complexity:{complexity}"]
        tier = self._task_tier(task)

        evidence_limited = evidence_score is not None and evidence_score < self.settings.routing_evidence_threshold
        low_confidence = confidence is not None and confidence < self.settings.routing_confidence_threshold
        if evidence_limited:
            # A stronger model cannot manufacture missing evidence. Keep cost bounded;
            # downstream claim controls still abstain when support is insufficient.
            tier = "standard" if tier == "premium" else tier
            reasons.append("evidence_limited_no_premium_escalation")
        elif low_confidence:
            tier = "premium"
            reasons.append("low_confidence_with_usable_evidence")
        elif complexity == "high":
            tier = "premium"
            reasons.append("high_complexity")
        elif complexity == "medium" and tier == "cheap":
            tier = "standard"
            reasons.append("medium_complexity")
        else:
            reasons.append("cheap_first_safe" if tier == "cheap" else "task_default")
        return tier, reasons

    def _task_tier(self, task: str) -> str:
        if task in _csv_set(self.settings.routing_premium_tasks):
            return "premium"
        if task in _csv_set(self.settings.routing_standard_tasks):
            return "standard"
        if task in _csv_set(self.settings.routing_cheap_tasks):
            return "cheap"
        return "standard"

    @staticmethod
    def _complexity(
        *,
        task: str,
        explicit: Any,
        estimated_input_tokens: int,
        input_budget: int,
        tool_count: int,
    ) -> str:
        normalized = str(explicit or "").strip().lower()
        if normalized not in COMPLEXITY_LEVELS:
            if task in {"complex_rag", "agentic_workflow"}:
                normalized = "high"
            elif task in {"simple_rag", "product_search"}:
                normalized = "medium"
            else:
                normalized = "low"
        utilization = estimated_input_tokens / max(1, input_budget)
        if tool_count >= 4 or utilization >= 0.8:
            normalized = "high"
        elif (tool_count >= 2 or utilization >= 0.5) and normalized == "low":
            normalized = "medium"
        return normalized

    def _available_target(self, requested_tier: str, configured: RoutingTarget) -> tuple[RoutingTarget, bool]:
        fallback_order = {
            "premium": ("premium", "standard", "cheap"),
            "standard": ("standard", "cheap"),
            "cheap": ("cheap",),
        }[requested_tier]
        for tier in fallback_order:
            target = self.targets[tier]
            if target.available and target.provider and target.model:
                return target, tier != requested_tier
        return configured, True

    def _provider_available(self, provider: str) -> bool:
        provider = provider.strip().lower()
        if provider == "ollama":
            return True
        if provider == "openrouter":
            return bool(self.settings.openrouter_api_key and self.settings.openrouter_api_key != "dummy")
        if provider == "deepseek":
            return bool(self.settings.deepseek_api_key)
        if provider in {"kimi", "moonshot"}:
            return bool(self.settings.kimi_api_key)
        return False


def _score(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return None


def _csv_set(value: str) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}
