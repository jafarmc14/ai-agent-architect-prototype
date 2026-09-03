from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthenticatedUser, RequestContext  # noqa: E402
from core.cost_governance import CostGovernanceService  # noqa: E402
from core.llm.model_routing import ModelRouter  # noqa: E402


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


def test_tracks_request_session_customer_and_tenant_costs():
    service = CostGovernanceService(
        settings=_cost_settings(budget=20), use_postgres=False, clock=lambda: NOW,
    )
    first = service.record(_guard("tenant-a", "session-a", "customer-a", 1.25))
    second = service.record(_guard("tenant-a", "session-a", "customer-a", 0.75))
    third = service.record(_guard("tenant-a", "session-b", "customer-a", 2.0))
    fourth = service.record(_guard("tenant-a", "session-c", "customer-b", 1.0))

    assert first.request_cost_usd == 1.25
    assert second.session_cost_usd == 2.0
    assert third.customer_cost_usd == 4.0
    assert fourth.request_cost_usd == 1.0
    assert fourth.session_cost_usd == 1.0
    assert fourth.customer_cost_usd == 1.0
    assert fourth.tenant_cost_usd == 5.0
    assert fourth.period == "2026-09"


def test_warns_at_80_percent_and_marks_exhausted_at_100_percent():
    service = CostGovernanceService(
        settings=_cost_settings(budget=10, threshold=0.8), use_postgres=False, clock=lambda: NOW,
    )
    warning = service.record(_guard("tenant-a", "session-a", "customer-a", 8.0))
    exhausted = service.record(_guard("tenant-a", "session-a", "customer-a", 2.0))

    assert warning.status == "warning"
    assert warning.warning is True
    assert warning.utilization_ratio == 0.8
    assert exhausted.status == "exhausted"
    assert exhausted.exhausted is True
    assert exhausted.utilization_ratio == 1.0


def test_budget_pressure_routes_cheap_and_exhaustion_restricts_premium():
    router = ModelRouter(_routing_settings(enabled=False))
    warning = _route(router, "warning", 0.8)
    exhausted = _route(router, "exhausted", 1.1)

    assert (warning.selected_tier, warning.provider) == ("cheap", "openrouter")
    assert "budget_forced_cheap" in warning.reasons
    assert exhausted.selected_tier == "cheap"
    assert exhausted.premium_model_used is False
    assert exhausted.premium_restricted is True
    assert exhausted.budget_utilization_ratio == 1.1


def test_exhausted_budget_blocks_when_only_premium_is_available():
    settings = _routing_settings(enabled=True)
    settings.openrouter_api_key = ""
    settings.deepseek_api_key = ""
    router = ModelRouter(settings)
    decision = _route(router, "exhausted", 1.0)

    assert decision.selected_tier == "blocked"
    assert decision.provider == ""
    assert decision.premium_restricted is True
    assert "no_non_premium_target_available" in decision.reasons


def test_budget_keeps_configured_local_provider_when_cheap_target_is_unavailable():
    settings = _routing_settings(enabled=False)
    settings.openrouter_api_key = ""
    router = ModelRouter(settings)
    decision = router.decide(
        task="agentic_workflow",
        base_provider="ollama",
        base_model="llama3.1",
        route_context={
            "cost_governance": {
                "enabled": True,
                "status": "warning",
                "utilization_ratio": 0.8,
            },
        },
    )

    assert decision.provider == "ollama"
    assert decision.model == "llama3.1"
    assert decision.premium_model_used is False


def _route(router, status: str, utilization: float):
    return router.decide(
        task="agentic_workflow",
        base_provider="kimi",
        base_model="kimi-k2.6",
        estimated_input_tokens=100,
        input_budget=1000,
        route_context={
            "complexity": "high",
            "confidence": 0.9,
            "evidence_score": 1.0,
            "cost_governance": {
                "enabled": True,
                "status": status,
                "utilization_ratio": utilization,
            },
        },
    )


def _cost_settings(*, budget: float, threshold: float = 0.8):
    return SimpleNamespace(
        database_provider="sqlite",
        cost_governance_enabled=True,
        tenant_monthly_ai_budget_usd=budget,
        tenant_monthly_ai_budget_warning_threshold=threshold,
    )


def _routing_settings(*, enabled: bool):
    return SimpleNamespace(
        model_routing_enabled=enabled,
        routing_cheap_provider="openrouter",
        routing_cheap_model="openrouter/free",
        routing_standard_provider="deepseek",
        routing_standard_model="deepseek-v4-flash",
        routing_premium_provider="kimi",
        routing_premium_model="kimi-k2.6",
        routing_cheap_tasks="intent,extraction,product_search,orders,cart,escalation",
        routing_standard_tasks="simple_rag",
        routing_premium_tasks="complex_rag,agentic_workflow",
        routing_confidence_threshold=0.7,
        routing_evidence_threshold=0.65,
        openrouter_api_key="configured",
        deepseek_api_key="configured",
        kimi_api_key="configured",
    )


def _guard(tenant_id: str, session_id: str, user_id: str, cost_usd: float):
    return SimpleNamespace(
        tenant_id=tenant_id,
        session_id=session_id,
        user_id=user_id,
        cost_usd=cost_usd,
    )


if __name__ == "__main__":
    test_tracks_request_session_customer_and_tenant_costs()
    test_warns_at_80_percent_and_marks_exhausted_at_100_percent()
    test_budget_pressure_routes_cheap_and_exhaustion_restricts_premium()
    test_exhausted_budget_blocks_when_only_premium_is_available()
    test_budget_keeps_configured_local_provider_when_cheap_target_is_unavailable()
    print("Cost governance tests passed.")
