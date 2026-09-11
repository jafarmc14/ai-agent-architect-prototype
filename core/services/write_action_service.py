from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any
from uuid import uuid4
from configs import get_settings

from core.auth import RequestContext, get_request_context
from core.privacy import redact_for_logs

_CONFIRMATION_RE = re.compile(r"^\s*(confirm|yes|approve)\s+([0-9a-f]{6,12})\s*[.!]?\s*$", re.IGNORECASE)
from core.repositories.write_control_repository import WriteControlRepository


_PENDING_ACTIONS: dict[str, "PendingWriteAction"] = {}
_MEMORY_IDEMPOTENCY: dict[str, str] = {}


@dataclass(frozen=True)
class PendingWriteAction:
    confirmation_id: str
    idempotency_key: str
    action: str
    resource_type: str
    resource_id: str
    payload: dict[str, Any]
    request_id: str
    user_id: str | None
    tenant_id: str


class WriteActionService:
    """Controlled write-action helper for confirmation, idempotency, and audit."""

    def __init__(self, repository: WriteControlRepository | None = None):
        self.repository = repository or WriteControlRepository()

    def prepare_confirmation(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: dict[str, Any],
        prompt: str,
    ) -> str:
        context = get_request_context()
        request_id = _request_id(context)
        idempotency_key = build_idempotency_key(context, action, resource_type, resource_id, payload)
        existing_response = self.find_existing_response(idempotency_key, context)
        if existing_response:
            return existing_response

        confirmation_id = uuid4().hex[:8]
        if get_settings().database_provider == "postgres":
            idempotency_key = sha256(f"{idempotency_key}:{confirmation_id}".encode()).hexdigest()
        pending = PendingWriteAction(
            confirmation_id=confirmation_id,
            idempotency_key=idempotency_key,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
            request_id=request_id,
            user_id=context.user_id,
            tenant_id=context.tenant_id,
        )
        if get_settings().database_provider == "postgres":
            from core.services.action_approvals import save_pending
            save_pending(pending)
        else:
            _PENDING_ACTIONS[_pending_key(context, confirmation_id)] = pending
        return (
            f"Confirmation required for {action}. {prompt}\n"
            "No mutation has been performed yet.\n"
            f"Reply with: confirm {confirmation_id}"
        )

    def consume_confirmation(self, message: str) -> PendingWriteAction | None:
        normalized = (message or "").strip()
        if normalized.startswith("**") and normalized.endswith("**"):
            normalized = normalized[2:-2].strip()
        match = _CONFIRMATION_RE.fullmatch(normalized)
        if not match:
            return None
        confirmation_id = match.group(2)
        if get_settings().database_provider == "postgres":
            from core.services.action_approvals import confirm_pending
            row = confirm_pending(confirmation_id.lower())
            if row:
                row["user_id"] = str(row["user_id"]) if row["user_id"] else None
                return PendingWriteAction(**row)
            return None
        return _PENDING_ACTIONS.pop(_pending_key(get_request_context(), confirmation_id), None)

    def find_existing_response(self, idempotency_key: str, context: RequestContext | None = None) -> str:
        context = context or get_request_context()
        cache_key = f"{context.tenant_id}:{context.user_id or context.session_id}:{idempotency_key}"
        postgres = get_settings().database_provider == "postgres"
        if not postgres and cache_key in _MEMORY_IDEMPOTENCY:
            return _MEMORY_IDEMPOTENCY[cache_key]
        try:
            record = self.repository.find_idempotency_record(idempotency_key, tenant_id=context.tenant_id)
        except Exception:  # noqa: BLE001
            if postgres:
                raise
            record = None
        if record and record.get("response"):
            if not postgres:
                _MEMORY_IDEMPOTENCY[cache_key] = record["response"]
            return record["response"]
        return ""

    def record_success(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
        response: str,
        idempotency_key: str,
        request_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        context = get_request_context()
        request_id = request_id or _request_id(context)
        from core.services.decision_audit import safe_value
        safe_old_value = safe_value(old_value or {})
        safe_new_value = safe_value(new_value or {})
        try:
            self.repository.record_idempotency(
                idempotency_key=idempotency_key,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=request_id,
                user_id=context.user_id,
                tenant_id=context.tenant_id,
                response=response,
                metadata=metadata or {},
            )
            self.repository.insert_audit_log(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                old_value=safe_old_value,
                new_value=safe_new_value,
                request_id=request_id,
                idempotency_key=idempotency_key,
                actor_user_id=context.user_id,
                actor_role=context.role,
                tenant_id=context.tenant_id,
                metadata=metadata or {},
            )
        except Exception:  # noqa: BLE001
            if get_settings().database_provider == "postgres":
                raise
        if get_settings().database_provider != "postgres":
            cache_key = f"{context.tenant_id}:{context.user_id or context.session_id}:{idempotency_key}"
            _MEMORY_IDEMPOTENCY[cache_key] = response


def build_idempotency_key(
    context: RequestContext,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload": payload,
        },
        sort_keys=True,
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _pending_key(context: RequestContext, confirmation_id: str) -> str:
    return f"{context.tenant_id}:{context.user_id or context.session_id}:{confirmation_id}"


def _request_id(context: RequestContext) -> str:
    return context.request_id or f"{context.session_id}:{uuid4().hex[:12]}"


write_action_service = WriteActionService()
