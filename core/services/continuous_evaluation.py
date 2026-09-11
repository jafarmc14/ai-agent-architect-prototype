from core.repositories.postgres_connection import get_postgres_connection
from core.services.decision_audit import review_categories


def link_regression(tenant_id, incident_id, case_id, reviewer):
    """Operator-reviewed labels only; production output is never an automatic gold answer."""
    import json
    from pathlib import Path
    from uuid import UUID
    UUID(incident_id)
    if not tenant_id.strip() or not reviewer.strip():
        raise ValueError("Tenant and reviewer are required")
    dataset = Path(__file__).resolve().parents[2] / "evaluation/datasets/regression/bugs.jsonl"
    ids = {json.loads(line)["id"] for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()}
    if case_id not in ids:
        raise ValueError("Add and review the regression case in bugs.jsonl first")
    with get_postgres_connection() as conn:
        return conn.execute("""UPDATE incident_cases SET status = 'regression_linked',
            regression_case_id = %s, reviewed_by = %s, reviewed_at = now()
            WHERE tenant_id = %s AND id = %s AND status = 'pending_review' RETURNING id""",
            (case_id, reviewer, tenant_id, incident_id)).fetchone() is not None


def sample_requests(tenant_id, *, limit=500):
    if not tenant_id or not 1 <= limit <= 5000:
        raise ValueError("Explicit tenant and limit between 1 and 5000 required")
    with get_postgres_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("evaluation:" + tenant_id,))
        rows = conn.execute("""SELECT q.request_id, q.metrics,
            (SELECT sum(l.total_tokens) FROM llm_requests l
             WHERE l.request_id = q.request_id AND l.tenant_id = q.tenant_id) AS tokens,
            EXISTS (SELECT 1 FROM pilot_feedback f WHERE f.request_id = q.request_id
                AND f.tenant_id = q.tenant_id AND f.kind IN ('thumbs_down', 'wrong_answer', 'report_issue')) AS negative
            FROM production_quality_events q WHERE q.tenant_id = %s
            AND (q.evaluation_sampled_at IS NULL OR EXISTS (
                SELECT 1 FROM pilot_feedback f WHERE f.request_id = q.request_id AND f.tenant_id = q.tenant_id
                AND (f.evaluation_sampled_at IS NULL OR f.updated_at > f.evaluation_sampled_at)))
            ORDER BY q.created_at, q.request_id LIMIT %s FOR UPDATE OF q""", (tenant_id, limit)).fetchall()
        count = 0
        for row in rows:
            for category in review_categories(row["request_id"], row["metrics"], tokens=row["tokens"],
                                              negative_feedback=row["negative"]):
                inserted = conn.execute("""INSERT INTO incident_cases (tenant_id, request_id, category)
                    VALUES (%s, %s, %s) ON CONFLICT (tenant_id, request_id, category) DO NOTHING RETURNING id""",
                    (tenant_id, row["request_id"], category)).fetchone()
                count += bool(inserted)
            conn.execute("UPDATE production_quality_events SET evaluation_sampled_at = now() WHERE tenant_id = %s AND request_id = %s",
                         (tenant_id, row["request_id"]))
            conn.execute("UPDATE pilot_feedback SET evaluation_sampled_at = now() WHERE tenant_id = %s AND request_id = %s",
                         (tenant_id, row["request_id"]))
    return {"requests_scanned": len(rows), "review_candidates_created": count}
