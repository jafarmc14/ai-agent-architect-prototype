import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any

from configs import get_settings
from core.repositories.cost_governance_repository import CostGovernanceRepository


@dataclass(frozen=True)
class CostSnapshot:
    enabled: bool
    request_cost_usd: float
    session_cost_usd: float
    customer_cost_usd: float
    tenant_cost_usd: float
    monthly_budget_usd: float
    utilization_ratio: float
    warning_threshold: float
    warning: bool
    exhausted: bool
    status: str
    budget_source: str
    period: str

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _MemoryCost:
    tenant_id: str
    session_id: str
    user_id: str
    cost_usd: float
    created_at: datetime


class CostGovernanceService:
    def __init__(self, settings=None, repository=None, use_postgres: bool | None = None, clock=None):
        self.settings = settings or get_settings()
        self.repository = repository or CostGovernanceRepository()
        self.use_postgres = (
            self.settings.database_provider == "postgres" if use_postgres is None else use_postgres
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._events: list[_MemoryCost] = []
        self._lock = threading.RLock()

    def assess(self, context, request_cost_usd: float = 0.0) -> CostSnapshot:
        now = self.clock()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        policy = self.repository.budget_for_tenant(
            context.tenant_id or "default",
            default_budget_usd=self.settings.tenant_monthly_ai_budget_usd,
            default_warning_threshold=self.settings.tenant_monthly_ai_budget_warning_threshold,
        ) if self.use_postgres else {
            "monthly_budget_usd": self.settings.tenant_monthly_ai_budget_usd,
            "warning_threshold": self.settings.tenant_monthly_ai_budget_warning_threshold,
            "enabled": True,
            "source": "environment_default",
        }
        costs = (
            self.repository.aggregate_month(
                tenant_id=context.tenant_id or "default",
                session_id=context.session_id,
                user_id=context.user_id,
                month_start=month_start,
            )
            if self.use_postgres else self._aggregate_memory(context, month_start)
        )
        tenant_cost = costs["tenant_cost_usd"] + max(0.0, float(request_cost_usd))
        budget = max(0.0, float(policy["monthly_budget_usd"]))
        utilization = tenant_cost / budget if budget > 0 else (1.0 if tenant_cost > 0 else 0.0)
        policy_enabled = bool(self.settings.cost_governance_enabled and policy["enabled"])
        exhausted = policy_enabled and (budget <= 0 or utilization >= 1.0)
        warning = policy_enabled and not exhausted and utilization >= float(policy["warning_threshold"])
        status = "exhausted" if exhausted else "warning" if warning else "normal" if policy_enabled else "disabled"
        return CostSnapshot(
            enabled=policy_enabled,
            request_cost_usd=round(max(0.0, float(request_cost_usd)), 10),
            session_cost_usd=round(costs["session_cost_usd"] + max(0.0, float(request_cost_usd)), 10),
            customer_cost_usd=round(
                costs["customer_cost_usd"] + (max(0.0, float(request_cost_usd)) if context.user_id else 0.0), 10
            ),
            tenant_cost_usd=round(tenant_cost, 10),
            monthly_budget_usd=budget,
            utilization_ratio=round(utilization, 6),
            warning_threshold=float(policy["warning_threshold"]),
            warning=warning,
            exhausted=exhausted,
            status=status,
            budget_source=policy["source"],
            period=month_start.strftime("%Y-%m"),
        )

    def record(self, guard) -> CostSnapshot:
        if not self.use_postgres:
            with self._lock:
                self._events.append(_MemoryCost(
                    tenant_id=guard.tenant_id,
                    session_id=guard.session_id,
                    user_id=guard.user_id or "",
                    cost_usd=max(0.0, float(guard.cost_usd)),
                    created_at=self.clock(),
                ))
        context = _GuardContext(guard)
        snapshot = self.assess(context, request_cost_usd=0.0)
        return replace(snapshot, request_cost_usd=round(max(0.0, float(guard.cost_usd)), 10))

    def _aggregate_memory(self, context, month_start: datetime) -> dict[str, float]:
        with self._lock:
            events = [
                event for event in self._events
                if event.created_at >= month_start and event.tenant_id == (context.tenant_id or "default")
            ]
        return {
            "tenant_cost_usd": sum(event.cost_usd for event in events),
            "session_cost_usd": sum(event.cost_usd for event in events if event.session_id == context.session_id),
            "customer_cost_usd": sum(
                event.cost_usd for event in events if context.user_id and event.user_id == context.user_id
            ),
        }


class _GuardContext:
    def __init__(self, guard):
        self.tenant_id = guard.tenant_id
        self.session_id = guard.session_id
        self.user_id = guard.user_id


cost_governance_service = CostGovernanceService()
