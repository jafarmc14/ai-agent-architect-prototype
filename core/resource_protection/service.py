import hashlib
import re
import threading
import time
from collections import deque
from dataclasses import dataclass

from configs import get_settings
from core.cost_governance import CostGovernanceService, cost_governance_service
from core.optimization import estimate_tokens
from core.repositories.resource_usage_repository import ResourceUsageRepository
from core.workflows import route_intent

from .models import (
    EXPENSIVE_WORKFLOWS,
    WORKFLOW_REQUEST_LIMITS,
    RequestResourceGuard,
    ResourceLimitExceeded,
    ResourceLimits,
)


@dataclass
class _MemoryEvent:
    timestamp: float
    request_id: str
    identity_key: str
    tenant_id: str
    workflow: str
    input_hash: str
    input_tokens: int
    output_tokens: int = 0
    cost_usd: float = 0.0
    status: str = "accepted"


class ResourceProtectionService:
    def __init__(
        self,
        limits: ResourceLimits | None = None,
        repository: ResourceUsageRepository | None = None,
        use_postgres: bool | None = None,
        workflow_limits: dict[str, int] | None = None,
        cost_service: CostGovernanceService | None = None,
    ):
        self.limits = limits or ResourceLimits.from_settings(get_settings())
        self.repository = repository or ResourceUsageRepository()
        self.use_postgres = (
            get_settings().database_provider == "postgres" if use_postgres is None else use_postgres
        )
        self.workflow_limits = dict(workflow_limits or WORKFLOW_REQUEST_LIMITS)
        self.cost_service = cost_service or (
            cost_governance_service if self.use_postgres else CostGovernanceService(use_postgres=False)
        )
        self._events: deque[_MemoryEvent] = deque()
        self._lock = threading.RLock()

    def begin_request(self, user_input: str, context, workflow: str | None = None) -> RequestResourceGuard:
        input_tokens = estimate_tokens(user_input)
        if input_tokens > self.limits.max_input_tokens:
            raise ResourceLimitExceeded("max_input_tokens", "Maximum user input tokens exceeded.")

        workflow = workflow or route_intent(user_input).workflow
        identity_key = f"user:{context.user_id}" if context.user_id else f"session:{context.session_id}"
        tenant_id = context.tenant_id or "default"
        input_hash = _input_hash(user_input)
        workflow_limit = self.workflow_limits.get(workflow, self.limits.user_rate_limit_requests)
        expensive = workflow in EXPENSIVE_WORKFLOWS
        cost_snapshot = self.cost_service.assess(context)

        if self.use_postgres:
            allowed, code, retry_after = self.repository.admit(
                request_id=context.request_id,
                trace_id=context.trace_id,
                tenant_id=tenant_id,
                identity_key=identity_key,
                session_id=context.session_id,
                user_id=context.user_id,
                workflow=workflow,
                input_hash=input_hash,
                input_tokens=input_tokens,
                limits=self.limits,
                workflow_limit=workflow_limit,
                expensive=expensive,
            )
        else:
            allowed, code, retry_after = self._admit_memory(
                context.request_id,
                identity_key,
                tenant_id,
                workflow,
                input_hash,
                input_tokens,
                workflow_limit,
                expensive,
            )
        if not allowed:
            raise ResourceLimitExceeded(code, f"Resource admission denied: {code}.", retry_after)

        return RequestResourceGuard(
            limits=self.limits,
            request_id=context.request_id,
            identity_key=identity_key,
            tenant_id=tenant_id,
            session_id=context.session_id,
            user_id=context.user_id,
            workflow=workflow,
            input_hash=input_hash,
            input_tokens=input_tokens,
            started_at=time.monotonic(),
            cost_governance=cost_snapshot.metadata(),
        )

    def finish_request(self, guard: RequestResourceGuard, status: str = "completed", limit_code: str = "") -> None:
        if self.use_postgres:
            self.repository.finish(guard, status=status, limit_code=limit_code)
            guard.cost_governance = self.cost_service.record(guard).metadata()
            self.repository.set_cost_governance(guard.request_id, guard.cost_governance)
            return
        with self._lock:
            for event in reversed(self._events):
                if (
                    event.request_id == guard.request_id
                    and event.identity_key == guard.identity_key
                    and event.input_hash == guard.input_hash
                    and event.status == "accepted"
                ):
                    event.output_tokens = guard.output_tokens
                    event.cost_usd = guard.cost_usd
                    event.status = status
                    break
        guard.cost_governance = self.cost_service.record(guard).metadata()

    def _admit_memory(
        self, request_id, identity, tenant, workflow, input_hash, input_tokens, workflow_limit, expensive
    ):
        now = time.time()
        with self._lock:
            while self._events and self._events[0].timestamp < now - 86400:
                self._events.popleft()
            accepted = [event for event in self._events if event.status != "blocked"]
            user_count = sum(
                event.identity_key == identity and event.timestamp >= now - self.limits.user_rate_limit_window_seconds
                for event in accepted
            )
            workflow_count = sum(
                event.identity_key == identity and event.workflow == workflow
                and event.timestamp >= now - self.limits.user_rate_limit_window_seconds
                for event in accepted
            )
            tenant_events = [event for event in accepted if event.tenant_id == tenant]
            repeat_count = sum(
                event.identity_key == identity and event.workflow == workflow and event.input_hash == input_hash
                and event.timestamp >= now - self.limits.expensive_repeat_window_seconds
                for event in accepted
            )
            code = ""
            retry = None
            reserved_cost = (
                input_tokens * self.limits.max_input_price_per_million
                + self.limits.max_output_tokens * self.limits.max_output_price_per_million
            ) / 1_000_000
            if user_count >= self.limits.user_rate_limit_requests:
                code, retry = "user_rate_limit", self.limits.user_rate_limit_window_seconds
            elif workflow_count >= workflow_limit:
                code, retry = "workflow_rate_limit", self.limits.user_rate_limit_window_seconds
            elif len(tenant_events) >= self.limits.tenant_daily_request_quota:
                code, retry = "tenant_request_quota", 3600
            elif sum(event.input_tokens + event.output_tokens for event in tenant_events) + input_tokens > self.limits.tenant_daily_token_quota:
                code, retry = "tenant_token_quota", 3600
            elif (
                sum(event.cost_usd for event in tenant_events) + reserved_cost
                > self.limits.tenant_daily_cost_quota_usd
            ):
                code, retry = "tenant_cost_quota", 3600
            elif expensive and repeat_count >= self.limits.expensive_repeat_limit:
                code, retry = "repetitive_expensive_request", self.limits.expensive_repeat_window_seconds
            self._events.append(_MemoryEvent(
                timestamp=now,
                request_id=request_id,
                identity_key=identity,
                tenant_id=tenant,
                workflow=workflow,
                input_hash=input_hash,
                input_tokens=input_tokens,
                cost_usd=0 if code else reserved_cost,
                status="blocked" if code else "accepted",
            ))
            return not code, code, retry


def _input_hash(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


resource_protection_service = ResourceProtectionService()
