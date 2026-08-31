from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from core.auth import RequestContext, get_request_context
from core.privacy import redact_for_logs
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
        _PENDING_ACTIONS[_pending_key(context, confirmation_id)] = PendingWriteAction(
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
        return (
            f"Confirmation required for {action}. {prompt}\n"
            "No mutation has been performed yet.\n"
            f"Reply with: confirm {confirmation_id}"
        )

    def consume_confirmation(self, message: str) -> PendingWriteAction | None:
        context = get_request_context()
        parts = message.strip().lower().split()
        if len(parts) < 2 or parts[0] not in {"confirm", "yes", "approve"}:
            return None
        confirmation_id = parts[1]
        return _PENDING_ACTIONS.pop(_pending_key(context, confirmation_id), None)

    def find_existing_response(self, idempotency_key: str, context: RequestContext | None = None) -> str:
        context = context or get_request_context()
        if idempotency_key in _MEMORY_IDEMPOTENCY:
            return _MEMORY_IDEMPOTENCY[idempotency_key]
        try:
            record = self.repository.find_idempotency_record(idempotency_key, tenant_id=context.tenant_id)
        except Exception:  # noqa: BLE001
            record = None
        if record and record.get("response"):
            _MEMORY_IDEMPOTENCY[idempotency_key] = record["response"]
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
        safe_old_value = redact_for_logs(old_value or {})
        safe_new_value = redact_for_logs(new_value or {})
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
            pass
        _MEMORY_IDEMPOTENCY[idempotency_key] = response


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
    return f"{context.session_id}:{uuid4().hex[:12]}"


write_action_service = WriteActionService()
