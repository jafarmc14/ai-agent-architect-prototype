from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from core.repositories.postgres_connection import get_postgres_connection


class ProductionMonitoringRepository:
    def record(self, request_id, tenant_id, metrics):
        with get_postgres_connection() as conn:
            conn.execute("""INSERT INTO production_quality_events (request_id, tenant_id, metrics)
                         VALUES (%s, %s, %s) ON CONFLICT (request_id) DO NOTHING""",
                         (request_id, tenant_id, Jsonb(metrics)))

    def review(self, request_id, tenant_id, reviewer, review):
        with get_postgres_connection() as conn:
            return conn.execute("""UPDATE production_quality_events SET review = %s, reviewed_by = %s, reviewed_at = now()
                                WHERE request_id = %s AND tenant_id = %s RETURNING request_id""",
                                (Jsonb(review), reviewer, request_id, tenant_id)).fetchone() is not None

    def rows(self, tenant_id, days=7):
        now = datetime.now(timezone.utc)
        with get_postgres_connection() as conn:
            rows = conn.execute(
                """SELECT q.request_id, q.created_at, q.metrics, q.review, r.user_id, r.latency_ms, r.status,
                          CASE WHEN u.calls = 0 AND COALESCE((q.metrics->>'llm_calls')::int, 0) = 0 THEN 0
                               WHEN u.calls >= (q.metrics->>'llm_calls')::int AND u.unknown_tokens = 0 THEN u.tokens END AS tokens,
                          CASE WHEN u.calls = 0 AND COALESCE((q.metrics->>'llm_calls')::int, 0) = 0 THEN 0
                               WHEN u.calls >= (q.metrics->>'llm_calls')::int AND u.unknown_cost = 0 THEN u.cost END AS cost_usd,
                          f.negative AS negative_feedback
                   FROM production_quality_events q JOIN request_traces r USING (request_id)
                   LEFT JOIN LATERAL (
                       SELECT count(*) AS calls, sum(prompt_tokens + completion_tokens) AS tokens, sum(cost_usd) AS cost,
                              count(*) FILTER (WHERE prompt_tokens IS NULL OR completion_tokens IS NULL) AS unknown_tokens,
                              count(*) FILTER (WHERE cost_usd IS NULL) AS unknown_cost
                       FROM llm_requests l WHERE l.request_id = q.request_id
                   ) u ON true
                   LEFT JOIN LATERAL (
                       SELECT bool_or(kind IN ('thumbs_down','wrong_answer')) AS negative FROM pilot_feedback
                       WHERE request_id = q.request_id AND kind IN ('thumbs_up','thumbs_down','wrong_answer')
                   ) f ON true
                   WHERE q.tenant_id = %s AND q.created_at >= %s AND q.created_at < %s
                   ORDER BY q.created_at""", (tenant_id, now - timedelta(days=days*2), now),
            ).fetchall()
        midpoint = now - timedelta(days=days)
        return [r for r in rows if r["created_at"] < midpoint], [r for r in rows if r["created_at"] >= midpoint]

    def snapshot(self, tenant_id, fingerprints):
        with get_postgres_connection() as conn:
            previous = conn.execute("""SELECT fingerprints FROM production_drift_snapshots
                                    WHERE tenant_id = %s ORDER BY created_at DESC LIMIT 1""", (tenant_id,)).fetchone()
            conn.execute("INSERT INTO production_drift_snapshots (tenant_id, fingerprints) VALUES (%s, %s)",
                         (tenant_id, Jsonb(fingerprints)))
        return previous["fingerprints"] if previous else None

    def enqueue(self, request_id, tenant_id, experiment_id, payload, daily_limit):
        with get_postgres_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"shadow:{tenant_id}",))
                count = conn.execute("""SELECT count(*) AS n FROM shadow_jobs WHERE tenant_id = %s
                                     AND created_at >= now() - interval '1 day'""", (tenant_id,)).fetchone()["n"]
                if count >= daily_limit:
                    return False
                conn.execute("""INSERT INTO shadow_jobs (request_id, tenant_id, experiment_id, payload)
                             VALUES (%s,%s,%s,%s) ON CONFLICT (request_id, experiment_id) DO NOTHING""",
                             (request_id, tenant_id, experiment_id, Jsonb(payload)))
                return True

    def claim_shadow(self, tenant_id, experiment_id):
        with get_postgres_connection() as conn:
            with conn.transaction():
                conn.execute("""UPDATE shadow_jobs SET status = 'expired', payload = '{}', finished_at = now()
                             WHERE tenant_id = %s AND status IN ('pending','running')
                               AND created_at < now() - interval '15 minutes'""", (tenant_id,))
                return conn.execute("""UPDATE shadow_jobs SET status = 'running' WHERE id = (
                                    SELECT id FROM shadow_jobs WHERE tenant_id = %s AND experiment_id = %s
                                    AND status = 'pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
                                    RETURNING *""", (tenant_id, experiment_id)).fetchone()

    def finish_shadow(self, job_id, status, result):
        with get_postgres_connection() as conn:
            conn.execute("""UPDATE shadow_jobs SET status = %s, result = %s, payload = '{}', finished_at = now()
                         WHERE id = %s AND status = 'running'""", (status, Jsonb(result), job_id))

    def shadow_report(self, tenant_id, experiment_id):
        with get_postgres_connection() as conn:
            return conn.execute("""SELECT id, status, created_at, result FROM shadow_jobs
                                WHERE tenant_id = %s AND experiment_id = %s ORDER BY created_at DESC LIMIT 1000""",
                                (tenant_id, experiment_id)).fetchall()
