"""Runs with real PostgreSQL and rolls back all fixture writes."""
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.postgres_connection import get_postgres_connection
from core.repositories.production_monitoring_repository import ProductionMonitoringRepository
from core.services.production_drift import current_fingerprints
from evaluation.run_production_monitoring import dataset_candidates


def main():
    with get_postgres_connection() as conn:
        @contextmanager
        def connection():
            yield conn
        try:
            tenant = "monitoring-test-" + str(uuid4())
            ids = [str(uuid4()) for _ in range(3)]
            for request_id in ids:
                conn.execute("""INSERT INTO request_traces (request_id, trace_id, user_id, tenant_id, request_input,
                             status, latency_ms, finished_at) VALUES (%s,%s,'fixture',%s,'find shoes','success',50,now())""",
                             (request_id, str(uuid4()), tenant))
            with patch("core.repositories.production_monitoring_repository.get_postgres_connection", connection), \
                 patch("core.services.production_drift.get_postgres_connection", connection), \
                 patch("evaluation.run_production_monitoring.get_postgres_connection", connection):
                repo = ProductionMonitoringRepository()
                for request_id in ids:
                    repo.record(request_id, tenant, {"llm_calls": 1, "intent": "PRODUCT_SEARCH", "language_heuristic": "en"})
                conn.execute("UPDATE production_quality_events SET created_at = now() - interval '10 days' WHERE request_id = %s", (ids[0],))
                conn.execute("""INSERT INTO llm_requests (provider, model, request_id, status, prompt_tokens, completion_tokens, cost_usd, tenant_id)
                             VALUES ('test','test',%s,'success',20,10,0,%s)""", (ids[1], tenant))
                previous, current = repo.rows(tenant)
                assert len(previous) == 1 and len(current) == 2
                by_id = {str(row["request_id"]): row for row in current}
                assert by_id[ids[1]]["tokens"] == 30 and by_id[ids[1]]["cost_usd"] == 0
                assert by_id[ids[2]]["tokens"] is None and by_id[ids[2]]["cost_usd"] is None
                assert repo.rows("unrelated-tenant") == ([], [])
                assert not repo.review(ids[1], "other", "reviewer", {"correct": True})
                assert repo.review(ids[1], tenant, "reviewer", {"correct": True})
                fingerprints = current_fingerprints(tenant)
                assert repo.snapshot(tenant, fingerprints) is None
                assert repo.snapshot(tenant, fingerprints) == fingerprints
                assert repo.enqueue(ids[1], tenant, "exp", {"test": True}, 1)
                assert not repo.enqueue(ids[2], tenant, "exp", {"test": True}, 1)
                assert repo.claim_shadow("other", "exp") is None
                job = repo.claim_shadow(tenant, "exp")
                assert job and repo.claim_shadow(tenant, "exp") is None
                repo.finish_shadow(job["id"], "completed", {"candidate": {"cost_usd": None}})
                assert repo.shadow_report(tenant, "exp")[0]["status"] == "completed"
                assert conn.execute("SELECT payload FROM shadow_jobs WHERE id = %s", (job["id"],)).fetchone()["payload"] == {}
                candidates = dataset_candidates(tenant, 7, 1)
                assert len(candidates) == 1 and candidates[0]["review_required"]
                assert candidates[0]["expected_tool"] is None
                assert dataset_candidates("other", 7, 10) == []
        finally:
            conn.rollback()
    print("Production monitoring integration tests passed (fixtures rolled back).")


if __name__ == "__main__":
    main()
