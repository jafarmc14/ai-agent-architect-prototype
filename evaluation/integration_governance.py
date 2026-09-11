"""Real PostgreSQL audit/retention tests; all fixture changes rolled back."""
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.auth import AuthenticatedUser, RequestContext, request_context
from core.repositories.postgres_connection import get_postgres_connection
from core.repositories.decision_audit_repository import DecisionAuditRepository
from core.services.continuous_evaluation import link_regression, sample_requests
from core.services.decision_audit import snapshot
from core.services.retention import run_retention


def main():
    with get_postgres_connection() as conn:
        @contextmanager
        def connection():
            yield conn
        tenant = "audit-test-" + str(uuid4())
        other = "audit-other-" + str(uuid4())
        request_id = str(uuid4())
        context = RequestContext("test", tenant, AuthenticatedUser("reviewer", role="manager", tenant_id=tenant))
        try:
            with patch("core.repositories.decision_audit_repository.get_postgres_connection", connection), \
                 patch("core.services.retention.get_postgres_connection", connection), \
                 patch("core.services.continuous_evaluation.get_postgres_connection", connection):
                repo = DecisionAuditRepository()
                with request_context(context):
                    value = snapshot(context, {"request_id": request_id}, "Verified response", "success")
                    repo.record(value)
                    repo.record({**value, "final_response": "duplicate must not overwrite"})
                    record = repo.reconstruct(request_id)
                    assert record["integrity_verified"]
                    assert record["snapshot"]["final_response"] == "Verified response"
                other_context = RequestContext("test", other, AuthenticatedUser("reviewer", role="admin", tenant_id=other))
                with request_context(other_context):
                    assert repo.reconstruct(request_id) is None
                conn.execute("UPDATE decision_records SET created_at = now() - interval '400 days' WHERE tenant_id = %s", (tenant,))
                assert run_retention(tenant)["rows"]["decision_records"] == 1
                assert run_retention(other, apply=True)["rows"]["decision_records"] == 0
                conn.execute("INSERT INTO retention_holds (tenant_id, reason) VALUES (%s, 'fixture')", (tenant,))
                assert run_retention(tenant, apply=True)["held"]
                conn.execute("DELETE FROM retention_holds WHERE tenant_id = %s", (tenant,))
                assert run_retention(tenant, apply=True)["rows"]["decision_records"] == 1
                assert run_retention(tenant, apply=True)["rows"]["decision_records"] == 0
                conn.execute("INSERT INTO request_traces (request_id, trace_id, tenant_id) VALUES (%s,%s,%s)",
                             (request_id, str(uuid4()), tenant))
                conn.execute("INSERT INTO production_quality_events (request_id, tenant_id, metrics) VALUES (%s,%s,%s)",
                             (request_id, tenant, '{"escalated": true}'))
                assert sample_requests(other)["review_candidates_created"] == 0
                assert sample_requests(tenant)["review_candidates_created"] >= 1
                assert sample_requests(tenant)["review_candidates_created"] == 0
                incident_id = str(conn.execute("SELECT id FROM incident_cases WHERE tenant_id = %s AND category = 'escalation'", (tenant,)).fetchone()["id"])
                assert not link_regression(other, incident_id, "bug_010_out_of_scope_general_knowledge", "reviewer")
                assert link_regression(tenant, incident_id, "bug_010_out_of_scope_general_knowledge", "reviewer")
                assert not link_regression(tenant, incident_id, "bug_010_out_of_scope_general_knowledge", "reviewer")
                llm_id = str(uuid4())
                conn.execute("""INSERT INTO llm_requests
                    (id, tenant_id, provider, model, request_messages, response_text, status, total_tokens, cost_usd, created_at)
                    VALUES (%s,%s,'fixture','fixture','[]','sensitive example','success',9000,0.01,now() - interval '8 days')""", (llm_id, tenant))
                assert run_retention(tenant)["rows"]["llm_requests_content_scrubbed"] == 1
                assert conn.execute("SELECT response_text FROM llm_requests WHERE id = %s", (llm_id,)).fetchone()["response_text"] == "sensitive example"
                run_retention(tenant, apply=True)
                usage = conn.execute("SELECT response_text, total_tokens, cost_usd FROM llm_requests WHERE id = %s", (llm_id,)).fetchone()
                assert usage["response_text"] is None and usage["total_tokens"] == 9000 and float(usage["cost_usd"]) == 0.01
        finally:
            conn.rollback()
    print("Governance PostgreSQL integration tests passed.")


if __name__ == "__main__":
    main()
