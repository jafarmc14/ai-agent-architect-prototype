from core.repositories.postgres_connection import get_postgres_connection


class PilotRepository:
    def feedback(self, request_id: str, tenant_id: str, user_id: str, kind: str) -> dict:
        with get_postgres_connection() as conn:
            with conn.transaction():
                # Lock the owned request to serialize rating changes and ticket retries.
                owned = conn.execute(
                    """SELECT request_id FROM request_traces
                       WHERE request_id = %s AND tenant_id = %s AND user_id = %s
                         AND finished_at IS NOT NULL FOR UPDATE""",
                    (request_id, tenant_id, user_id),
                ).fetchone()
                if not owned:
                    raise LookupError("Request not found.")
                existing = conn.execute(
                    "SELECT ticket_number FROM pilot_feedback WHERE request_id = %s AND user_id = %s AND kind = %s",
                    (request_id, user_id, kind),
                ).fetchone()
                if existing:
                    return {"status": "saved", "kind": kind, "ticket_number": existing["ticket_number"]}
                if kind in {"thumbs_up", "thumbs_down"}:
                    conn.execute(
                        "DELETE FROM pilot_feedback WHERE request_id = %s AND user_id = %s AND kind IN ('thumbs_up', 'thumbs_down')",
                        (request_id, user_id),
                    )
                ticket = None
                if kind in {"request_human", "report_issue"}:
                    row = conn.execute(
                        """INSERT INTO support_tickets
                           (ticket_number, user_id, tenant_id, customer_message, agent_summary,
                            escalation_type, escalation_reason, metadata)
                           VALUES ('TICKET-' || upper(gen_random_uuid()::text), %s::uuid, %s, %s, %s,
                                   %s, 'Pilot feedback', jsonb_build_object('request_id', %s::text))
                           RETURNING ticket_number""",
                        (user_id, tenant_id, kind.replace('_', ' '),
                         f"Review pilot request {request_id}.",
                         "human_requested" if kind == "request_human" else "pilot_issue", request_id),
                    ).fetchone()
                    ticket = row["ticket_number"]
                conn.execute(
                    """INSERT INTO pilot_feedback (request_id, tenant_id, user_id, kind, ticket_number)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (request_id, tenant_id, user_id, kind, ticket),
                )
                return {"status": "saved", "kind": kind, "ticket_number": ticket}

    def usage(self, tenant_id: str, days: int) -> dict:
        with get_postgres_connection() as conn:
            daily = conn.execute(
                """SELECT (r.started_at AT TIME ZONE 'UTC')::date AS day,
                          count(*) AS requests, count(DISTINCT r.user_id) AS testers,
                          avg(r.latency_ms) AS avg_latency_ms,
                          percentile_cont(0.95) WITHIN GROUP (ORDER BY r.latency_ms) AS p95_latency_ms
                   FROM request_traces r
                   WHERE r.tenant_id = %s AND r.started_at >= now() - %s * interval '1 day'
                     AND r.metadata->>'pilot' = 'true'
                   GROUP BY 1 ORDER BY 1""", (tenant_id, days),
            ).fetchall()
            models = conn.execute(
                """SELECT l.provider, l.model, l.cost_source, r.workflow,
                          count(*) AS llm_calls, sum(l.prompt_tokens) AS input_tokens,
                          sum(l.completion_tokens) AS output_tokens,
                          count(*) FILTER (WHERE l.prompt_tokens IS NULL OR l.completion_tokens IS NULL) AS unknown_token_calls,
                          sum(l.cost_usd) AS known_cost_usd,
                          count(*) FILTER (WHERE l.cost_usd IS NULL) AS unknown_cost_calls,
                          avg(l.latency_ms) AS avg_latency_ms
                   FROM llm_requests l JOIN request_traces r ON r.request_id = l.request_id
                   WHERE r.tenant_id = %s AND r.started_at >= now() - %s * interval '1 day'
                     AND r.metadata->>'pilot' = 'true'
                   GROUP BY l.provider, l.model, l.cost_source, r.workflow
                   ORDER BY llm_calls DESC""", (tenant_id, days),
            ).fetchall()
            feedback = conn.execute(
                """SELECT f.kind, count(*) AS count FROM pilot_feedback f
                   JOIN request_traces r ON r.request_id = f.request_id
                   WHERE f.tenant_id = %s AND f.created_at >= now() - %s * interval '1 day'
                     AND r.metadata->>'pilot' = 'true'
                   GROUP BY f.kind ORDER BY f.kind""", (tenant_id, days),
            ).fetchall()
        return {"days": days, "daily": daily, "models": models, "feedback": feedback}
