from functools import wraps
from inspect import signature

from psycopg.types.json import Jsonb

from configs import get_settings
from core.auth import get_request_context
from core.repositories.postgres_connection import get_postgres_connection, mutation_transaction


def actor_id(context):
    return context.user_id or "session:" + context.session_id


def save_pending(pending):
    context = get_request_context()
    with get_postgres_connection() as conn:
        conn.execute("""INSERT INTO action_approvals
            (tenant_id, confirmation_id, idempotency_key, actor_id, actor_user_id, action,
             resource_type, resource_id, payload, request_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (context.tenant_id, pending.confirmation_id, pending.idempotency_key, actor_id(context),
             context.user_id, pending.action, pending.resource_type, pending.resource_id,
             Jsonb(pending.payload), pending.request_id))


def confirm_pending(confirmation_id):
    context = get_request_context()
    with get_postgres_connection() as conn:
        return conn.execute("""UPDATE action_approvals SET confirmed_at = COALESCE(confirmed_at, now())
            WHERE tenant_id = %s AND confirmation_id = %s AND actor_id = %s
              AND (expires_at > now() OR completed_at IS NOT NULL)
            RETURNING confirmation_id, idempotency_key, action, resource_type, resource_id,
                      payload, request_id, actor_user_id AS user_id, tenant_id""",
            (context.tenant_id, confirmation_id, actor_id(context))).fetchone()


def approve_pending(confirmation_id):
    context = get_request_context()
    if context.role not in {"manager", "admin"} or not context.user_id:
        raise PermissionError("Independent manager/admin approval is required")
    with get_postgres_connection() as conn:
        row = conn.execute("""UPDATE action_approvals SET approved_by = %s, approved_at = now()
            WHERE tenant_id = %s AND confirmation_id = %s AND actor_id != %s
              AND expires_at > now() AND completed_at IS NULL AND approved_by IS NULL
              AND action IN ('order.cancel','order.update_shipping_address')
            RETURNING idempotency_key, resource_id, action""",
            (context.user_id, context.tenant_id, confirmation_id, actor_id(context))).fetchone()
        if row:
            conn.execute("""INSERT INTO audit_logs
                (tenant_id, actor_user_id, actor_role, action, resource_type, resource_id, request_id, new_value)
                VALUES (%s,%s,%s,'action.approve','order',%s,%s,%s)""",
                (context.tenant_id, context.user_id, context.role, row["resource_id"], context.request_id,
                 Jsonb({"confirmation_id": confirmation_id, "action": row["action"]})))
        return bool(row)


def controlled_mutation(action):
    """One commit for mutation, audit and idempotency; failures roll back all three."""
    def decorate(function):
        parameters = signature(function)

        @wraps(function)
        def run(*args, **kwargs):
            bound = parameters.bind(*args, **kwargs)
            bound.apply_defaults()
            if get_settings().database_provider != "postgres" or not bound.arguments.get("confirmed"):
                return function(*args, **kwargs)
            context = get_request_context()
            from core.auth import authorize_tool
            tool_name = {"cart.add_item": "add_product_to_cart", "cart.clear": "clear_shopping_cart",
                         "order.cancel": "cancel_customer_order",
                         "order.update_shipping_address": "update_shipping_address"}[action]
            if not authorize_tool(tool_name, context).allowed:
                return "This action is no longer authorized. No mutation was performed."
            key = bound.arguments.get("idempotency_key")
            if not key:
                return "A valid confirmation is required. No mutation was performed."
            with mutation_transaction(f"{context.tenant_id}:{key}") as conn:
                if action.startswith("cart."):
                    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                                 (f"cart:{context.tenant_id}:{actor_id(context)}",))
                pending = conn.execute("""SELECT * FROM action_approvals
                    WHERE tenant_id = %s AND idempotency_key = %s AND actor_id = %s
                    AND action = %s FOR UPDATE""", (context.tenant_id, key, actor_id(context), action)).fetchone()
                if not pending or not pending["confirmed_at"]:
                    return "A valid confirmation is required. No mutation was performed."
                for name in ("order_id", "new_address", "product_name", "quantity"):
                    expected = pending["payload"].get(name)
                    if expected is not None and bound.arguments.get(name) != expected:
                        return "The proposed action changed. Please request a new confirmation."
                existing = conn.execute("""SELECT response FROM write_idempotency_keys
                    WHERE tenant_id = %s AND idempotency_key = %s""", (context.tenant_id, key)).fetchone()
                if existing:
                    return existing["response"]
                expired = conn.execute("SELECT %s::timestamptz <= now() AS expired", (pending["expires_at"],)).fetchone()["expired"]
                if expired:
                    return "The confirmation expired. No mutation was performed."
                if action.startswith("order.") and not pending["approved_by"]:
                    return "Independent manager approval is required. No mutation was performed."
                response = function(*args, **kwargs)
                completed = conn.execute("""SELECT 1 FROM write_idempotency_keys
                    WHERE tenant_id = %s AND idempotency_key = %s""", (context.tenant_id, key)).fetchone()
                if completed:
                    conn.execute("""UPDATE action_approvals SET completed_at = now()
                        WHERE tenant_id = %s AND idempotency_key = %s""", (context.tenant_id, key))
                return response
        return run
    return decorate
