"""PostgreSQL feedback and reporting checks; all fixture writes are rolled back."""
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.postgres_connection import get_postgres_connection
from core.repositories.pilot_repository import PilotRepository


def main():
    with get_postgres_connection() as conn:
        try:
            user = str(uuid4())
            tenant = f"pilot-test-{uuid4()}"
            request = str(uuid4())
            conn.execute("INSERT INTO users (id, name) VALUES (%s, 'Pilot fixture')", (user,))
            conn.execute(
                """INSERT INTO request_traces (request_id, trace_id, user_id, tenant_id, finished_at, metadata)
                   VALUES (%s, %s, %s, %s, now(), '{"pilot":true}')""",
                (request, str(uuid4()), user, tenant),
            )

            @contextmanager
            def connection():
                yield conn

            with patch("core.repositories.pilot_repository.get_postgres_connection", connection):
                repo = PilotRepository()
                for wrong_tenant, wrong_user in [(tenant, str(uuid4())), ("other", user)]:
                    try:
                        repo.feedback(request, wrong_tenant, wrong_user, "request_human")
                        raise AssertionError("Foreign request accepted")
                    except LookupError:
                        pass
                repo.feedback(request, tenant, user, "thumbs_up")
                repo.feedback(request, tenant, user, "thumbs_down")
                first = repo.feedback(request, tenant, user, "request_human")
                assert first["ticket_number"]
                assert repo.feedback(request, tenant, user, "request_human") == first
                repo.feedback(request, tenant, user, "report_issue")
                assert conn.execute("SELECT count(*) AS n FROM support_tickets WHERE tenant_id = %s", (tenant,)).fetchone()["n"] == 2
                conn.execute(
                    """INSERT INTO llm_requests (provider, model, status, request_id, prompt_tokens,
                       completion_tokens, cost_usd, cost_source)
                       VALUES ('test', 'local', 'success', %s, 20, 10, NULL, NULL),
                              ('test', 'free', 'success', %s, 30, 15, 0, 'provider')""",
                    (request, request),
                )
                report = repo.usage(tenant, 7)
                assert len(report["daily"]) == 1
                assert report["daily"][0]["requests"] == 1
                models = {row["model"]: row for row in report["models"]}
                assert models["local"]["known_cost_usd"] is None
                assert models["local"]["unknown_cost_calls"] == 1
                assert models["free"]["known_cost_usd"] == 0
                assert {row["kind"]: row["count"] for row in report["feedback"]} == {
                    "thumbs_down": 1, "request_human": 1, "report_issue": 1,
                }
                assert repo.usage("another-tenant", 7)["models"] == []
                conn.execute("UPDATE request_traces SET metadata = '{}' WHERE request_id = %s", (request,))
                excluded = repo.usage(tenant, 7)
                assert excluded["daily"] == excluded["models"] == excluded["feedback"] == []
                conn.execute("UPDATE request_traces SET finished_at = NULL WHERE request_id = %s", (request,))
                try:
                    repo.feedback(request, tenant, user, "wrong_answer")
                    raise AssertionError("Unfinished request accepted")
                except LookupError:
                    pass
        finally:
            conn.rollback()
    print("Pilot PostgreSQL integration tests passed (fixtures rolled back).")


if __name__ == "__main__":
    main()
