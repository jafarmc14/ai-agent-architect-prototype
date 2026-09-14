"""Real RLS, independent approval, rollback and concurrent retry tests."""
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import AuthenticatedUser, RequestContext, request_context
from core.auth.jwt import create_session_token
from api.main import app as api_app
from core.repositories.postgres_connection import get_postgres_connection
from core.services.action_approvals import approve_pending, reject_pending
from core.services.order_service import OrderService
from core.services.write_action_service import WriteActionService
from core.repositories.postgres_vector_repository import PostgresVectorRepository
from core.repositories.postgres_cart_repository import PostgresCartRepository


def main():
    actor, manager, other = [str(uuid4()) for _ in range(3)]
    order_id = "TEST-" + uuid4().hex
    rejected_order_id = "TEST-" + uuid4().hex
    document_ids = [str(uuid4()), str(uuid4())]
    cart_session = "shared-fixture-" + uuid4().hex
    vector = [1.0] + [0.0] * 767
    customer = RequestContext("transaction-test", "default", AuthenticatedUser(actor, tenant_id="default"))
    reviewer = RequestContext("reviewer", "default", AuthenticatedUser(manager, role="manager", tenant_id="default"))
    foreign = RequestContext("foreign", "company_b", AuthenticatedUser(other, role="admin", tenant_id="company_b"))
    with get_postgres_connection() as conn:
        for uid, tenant in ((actor, "default"), (manager, "default"), (other, "company_b")):
            conn.execute("INSERT INTO users (id, tenant_id, name) VALUES (%s,%s,'fixture')", (uid, tenant))
        conn.execute("INSERT INTO orders (order_number, tenant_id, user_id, status) VALUES (%s,'default',%s,'processing')", (order_id, actor))
        conn.execute("INSERT INTO orders (order_number, tenant_id, user_id, status) VALUES (%s,'default',%s,'processing')", (rejected_order_id, actor))
        import json
        for document, tenant in zip(document_ids, ("default", "company_b")):
            conn.execute("""INSERT INTO documents (id, tenant_id, title, source, version, status, approval_status, metadata)
                VALUES (%s,%s,'Fixture policy',%s,'v1','active','indexed',
                '{"category":"faq","trust_level":"OFFICIAL","access_level":"public"}')""", (document, tenant, "fixture:" + document))
            conn.execute("""INSERT INTO document_chunks (document_id, tenant_id, chunk_index, content, embedding_model, embedding_vector)
                VALUES (%s,%s,0,%s,'fixture',%s::vector)""", (document, tenant, tenant + " private evidence", json.dumps(vector)))
    try:
        with request_context(foreign), get_postgres_connection() as conn:
            assert conn.execute("SELECT current_user AS role").fetchone()["role"] == "ai_agent_runtime"
            assert conn.execute("SELECT * FROM orders WHERE order_number = %s", (order_id,)).fetchone() is None
            try:
                with conn.transaction():
                    conn.execute("INSERT INTO orders (order_number, tenant_id, user_id, currency) VALUES (%s,'company_b',%s,'EUR')", ("BAD-" + uuid4().hex, actor))
            except Exception as exc:
                assert getattr(exc, "sqlstate", "") == "23503", str(exc)
            else:
                raise AssertionError("Cross-tenant reference accepted")
            try:
                with conn.transaction():
                    conn.execute("DELETE FROM audit_logs WHERE tenant_id = 'company_b'")
            except Exception as exc:
                assert getattr(exc, "sqlstate", "") == "42501", str(exc)
            else:
                raise AssertionError("Runtime can delete audit records")
        with request_context(foreign):
            rows = PostgresVectorRepository().search_chunks(vector, tenant_id="company_b", embedding_model="fixture")
            assert len(rows) == 1 and rows[0]["tenant_id"] == "company_b"
            assert PostgresVectorRepository().search_chunks(vector, tenant_id="default", embedding_model="fixture") == []
        carts = []
        for tenant in ("default", "company_a"):
            with request_context(RequestContext(cart_session, tenant)), get_postgres_connection() as conn:
                carts.append(PostgresCartRepository()._get_or_create_cart(conn, cart_session)["id"])
        assert carts[0] != carts[1]

        service = OrderService()
        with patch("core.services.order_service.get_settings", return_value=SimpleNamespace(high_risk_write_actions_enabled=True)):
            with request_context(customer):
                response = service.cancel_order(order_id)
                code = re.search(r"confirm ([0-9a-f]{8})", response).group(1)
                # A new service instance models restart: confirmation is not in memory.
                pending = WriteActionService().consume_confirmation(f"confirm {code}")
                assert pending is not None
                assert "manager approval" in service.cancel_order(order_id, True, pending.idempotency_key)
            with request_context(foreign):
                assert WriteActionService().consume_confirmation(f"confirm {code}") is None
                assert not approve_pending(code)
            with request_context(reviewer):
                assert approve_pending(code)
            with request_context(customer):
                with patch("core.repositories.write_control_repository.WriteControlRepository.insert_audit_log", side_effect=RuntimeError("audit unavailable")):
                    try:
                        service.cancel_order(order_id, True, pending.idempotency_key)
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError("Audit failure did not abort transaction")
                with get_postgres_connection() as conn:
                    assert conn.execute("SELECT status FROM orders WHERE order_number = %s", (order_id,)).fetchone()["status"] == "processing"
                    assert conn.execute("SELECT 1 FROM write_idempotency_keys WHERE idempotency_key = %s", (pending.idempotency_key,)).fetchone() is None
            def retry(_):
                with request_context(customer):
                    return service.cancel_order(order_id, True, pending.idempotency_key)
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(retry, range(2)))
            assert responses[0] == responses[1] and "successfully cancelled" in responses[0]
            with get_postgres_connection() as conn:
                assert conn.execute("SELECT count(*) AS n FROM audit_logs WHERE idempotency_key = %s", (pending.idempotency_key,)).fetchone()["n"] == 1
            with request_context(customer):
                response = service.cancel_order(rejected_order_id)
                rejected_code = re.search(r"confirm ([0-9a-f]{8})", response).group(1)
                rejected_pending = WriteActionService().consume_confirmation(f"confirm {rejected_code}")
                assert rejected_pending is not None
                try:
                    reject_pending(rejected_code)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Customer rejected their own request")
            with request_context(foreign):
                assert not reject_pending(rejected_code)
            client = TestClient(api_app)
            reviewer_headers = {"Authorization": "Bearer " + create_session_token(manager, "manager@fixture.local", "Manager", role="manager")}
            customer_headers = {"Authorization": "Bearer " + create_session_token(actor, "customer@fixture.local", "Customer")}
            waiting = client.get("/api/v1/governance/approvals", headers=reviewer_headers)
            assert waiting.status_code == 200, waiting.text
            listed = next(item for item in waiting.json() if item["confirmation_id"] == rejected_code)
            assert listed["order_status"] == "processing"
            assert client.post(f"/api/v1/governance/approvals/{rejected_code}/reject", headers=customer_headers).status_code == 403
            decision = client.post(f"/api/v1/governance/approvals/{rejected_code}/reject", headers=reviewer_headers)
            assert decision.status_code == 200 and decision.json() == {"status": "rejected", "executed": False}
            with request_context(reviewer):
                assert not reject_pending(rejected_code)
                assert not approve_pending(rejected_code)
            assert client.post(f"/api/v1/governance/approvals/{rejected_code}/reject", headers=reviewer_headers).status_code == 409
            assert rejected_code not in {item["confirmation_id"] for item in client.get(
                "/api/v1/governance/approvals", headers=reviewer_headers).json()}
            rejected_status = client.get(f"/api/v1/order-action-requests/{rejected_code}", headers=customer_headers)
            assert rejected_status.status_code == 200 and rejected_status.json()["state"] == "rejected"
            with request_context(customer):
                assert WriteActionService().consume_confirmation(f"confirm {rejected_code}") is None
                assert "not approved" in WriteActionService().rejected_confirmation_message(f"confirm {rejected_code}")
                result = service.cancel_order(rejected_order_id, True, rejected_pending.idempotency_key)
                assert "not approved" in result
                with get_postgres_connection() as conn:
                    assert conn.execute("SELECT status FROM orders WHERE order_number = %s", (rejected_order_id,)).fetchone()["status"] == "processing"
                    assert str(conn.execute("SELECT rejected_by FROM action_approvals WHERE confirmation_id = %s", (rejected_code,)).fetchone()["rejected_by"]) == manager
                    assert conn.execute("SELECT count(*) AS n FROM audit_logs WHERE action = 'action.reject' AND resource_id = %s", (rejected_order_id,)).fetchone()["n"] == 1
    finally:
        with get_postgres_connection() as conn:
            conn.execute("DELETE FROM shopping_carts WHERE session_id = %s", (cart_session,))
            conn.execute("DELETE FROM document_chunks WHERE document_id = ANY(%s::uuid[])", (document_ids,))
            conn.execute("DELETE FROM documents WHERE id = ANY(%s::uuid[])", (document_ids,))
            conn.execute("DELETE FROM action_approvals WHERE resource_id = ANY(%s::text[])", ([order_id, rejected_order_id],))
            conn.execute("DELETE FROM write_idempotency_keys WHERE resource_id = ANY(%s::text[])", ([order_id, rejected_order_id],))
            conn.execute("DELETE FROM audit_logs WHERE resource_id = ANY(%s::text[])", ([order_id, rejected_order_id],))
            conn.execute("DELETE FROM orders WHERE order_number = ANY(%s::text[])", ([order_id, rejected_order_id],))
            conn.execute("DELETE FROM users WHERE id = ANY(%s::uuid[])", ([actor, manager, other],))
    print("Tenant RLS, approval, atomic audit rollback and concurrent retry tests passed.")


if __name__ == "__main__":
    main()
