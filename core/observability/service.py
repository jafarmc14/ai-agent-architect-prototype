import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from core.auth import RequestContext
from core.privacy import redact_for_logs
from core.repositories.observability_repository import ObservabilityRepository


LIFECYCLE_STAGES = {"request", "intent", "retrieval", "tool", "llm", "validation", "response"}


@dataclass
class RequestTrace:
    request_id: str
    trace_id: str
    runtime_trace: dict[str, Any] | None = None
    response_text: str = ""
    intent: str = ""
    workflow: str = ""
    conversation_id: str = ""
    status: str = "running"
    error_message: str = ""

    def complete(
        self,
        response_text: str,
        *,
        intent: str = "",
        workflow: str = "",
        conversation_id: str = "",
    ) -> None:
        self.response_text = response_text
        self.intent = intent
        self.workflow = workflow
        self.conversation_id = conversation_id
        self.status = "success"


@dataclass
class TraceSpan:
    service: "ObservabilityService"
    stage: str
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    parent_span_id: str = ""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _start_counter: float = field(default_factory=time.perf_counter)

    def set_attributes(self, **attributes: Any) -> None:
        self.attributes.update(attributes)

    def finish(self, status: str = "success", error_message: str = "") -> None:
        self.service._finish_span(self, status=status, error_message=error_message)


_active_trace: ContextVar[RequestTrace | None] = ContextVar("active_observability_trace", default=None)


class ObservabilityService:
    """Best-effort request tracing that never changes application behavior."""

    def __init__(self, repository: ObservabilityRepository | None = None):
        self.repository = repository or ObservabilityRepository()

    @contextmanager
    def trace_request(
        self,
        user_input: str,
        context: RequestContext,
        runtime_trace: dict[str, Any] | None = None,
    ) -> Iterator[RequestTrace]:
        request_trace = RequestTrace(
            request_id=str(uuid.uuid4()),
            trace_id=str(uuid.uuid4()),
            runtime_trace=runtime_trace,
        )
        if runtime_trace is not None:
            runtime_trace["request_id"] = request_trace.request_id
            runtime_trace["trace_id"] = request_trace.trace_id
            runtime_trace.setdefault("lifecycle", [])

        started = time.perf_counter()
        try:
            self.repository.start_request(
                request_id=request_trace.request_id,
                trace_id=request_trace.trace_id,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                user_id=context.user_id or "",
                request_input=_bounded(user_input),
            )
        except Exception:  # noqa: BLE001
            pass
        token = _active_trace.set(request_trace)
        self.record_event("request", "request.received", attributes={"session_id": context.session_id})
        try:
            yield request_trace
        except Exception as exc:
            request_trace.status = "error"
            request_trace.error_message = str(exc)
            self.record_event("response", "response.failed", status="error", attributes={"error": str(exc)})
            raise
        finally:
            latency_ms = int(round((time.perf_counter() - started) * 1000))
            if request_trace.status == "running":
                request_trace.status = "success"
            if request_trace.status == "success":
                self.record_event(
                    "response",
                    "response.returned",
                    attributes={"response_length": len(request_trace.response_text)},
                )
            try:
                self.repository.finish_request(
                    request_id=request_trace.request_id,
                    status=request_trace.status,
                    response_output=_bounded(request_trace.response_text),
                    intent=request_trace.intent,
                    workflow=request_trace.workflow,
                    conversation_id=request_trace.conversation_id,
                    latency_ms=latency_ms,
                    error_message=_bounded(request_trace.error_message),
                )
            except Exception:  # noqa: BLE001
                pass
            if runtime_trace is not None:
                runtime_trace["request_status"] = request_trace.status
                runtime_trace["request_latency_ms"] = latency_ms
            _active_trace.reset(token)

    @contextmanager
    def span(
        self,
        stage: str,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
        parent_span_id: str = "",
    ) -> Iterator[TraceSpan]:
        if stage not in LIFECYCLE_STAGES:
            raise ValueError(f"Unsupported lifecycle stage: {stage}")
        span = TraceSpan(
            service=self,
            stage=stage,
            name=name,
            attributes=dict(attributes or {}),
            parent_span_id=parent_span_id,
        )
        try:
            yield span
        except Exception as exc:
            span.finish(status="error", error_message=str(exc))
            raise
        else:
            span.finish()

    def record_event(
        self,
        stage: str,
        name: str,
        *,
        status: str = "success",
        attributes: dict[str, Any] | None = None,
    ) -> None:
        span = TraceSpan(service=self, stage=stage, name=name, attributes=dict(attributes or {}))
        span.finish(status=status)

    def _finish_span(self, span: TraceSpan, *, status: str, error_message: str) -> None:
        active = _active_trace.get()
        if active is None:
            return
        latency_ms = int(round((time.perf_counter() - span._start_counter) * 1000))
        attributes = _safe_attributes(span.attributes)
        event = {
            "span_id": span.span_id,
            "stage": span.stage,
            "name": span.name,
            "status": status,
            "started_at": span.started_at.isoformat(),
            "latency_ms": latency_ms,
            "attributes": attributes,
        }
        if error_message:
            event["error"] = _bounded(error_message)
        if active.runtime_trace is not None:
            active.runtime_trace.setdefault("lifecycle", []).append(event)
        try:
            self.repository.insert_span(
                span_id=span.span_id,
                trace_id=active.trace_id,
                parent_span_id=span.parent_span_id,
                stage=span.stage,
                name=span.name,
                status=status,
                started_at=span.started_at,
                latency_ms=latency_ms,
                attributes=attributes,
                error_message=_bounded(error_message),
            )
        except Exception:  # noqa: BLE001
            pass


def current_trace_ids() -> dict[str, str]:
    active = _active_trace.get()
    if active is None:
        return {"request_id": "", "trace_id": ""}
    return {"request_id": active.request_id, "trace_id": active.trace_id}


def observed_span(
    stage: str,
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    parent_span_id: str = "",
):
    return observability_service.span(
        stage,
        name,
        attributes=attributes,
        parent_span_id=parent_span_id,
    )


def record_trace_event(
    stage: str,
    name: str,
    *,
    status: str = "success",
    attributes: dict[str, Any] | None = None,
) -> None:
    observability_service.record_event(stage, name, status=status, attributes=attributes)


def _safe_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_for_logs(attributes)
    return _bound_value(redacted)


def _bound_value(value: Any) -> Any:
    if isinstance(value, str):
        return _bounded(value)
    if isinstance(value, dict):
        return {str(key): _bound_value(item) for key, item in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [_bound_value(item) for item in list(value)[:50]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _bounded(str(value))


def _bounded(value: str, limit: int = 2000) -> str:
    redacted = redact_for_logs(value or "")
    return redacted if len(redacted) <= limit else f"{redacted[:limit]}..."


observability_service = ObservabilityService()
