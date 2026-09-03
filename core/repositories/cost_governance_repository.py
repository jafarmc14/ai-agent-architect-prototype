from datetime import datetime
from typing import Any

from configs import get_settings
from core.repositories.postgres_connection import get_postgres_connection


class CostGovernanceRepository:
    """Reads actual completed-request cost and optional per-tenant budget overrides."""

    def aggregate_month(
        self,
        *,
        tenant_id: str,
        session_id: str,
        user_id: str | None,
        month_start: datetime,
    ) -> dict[str, float]:
        if get_settings().database_provider != "postgres":
            raise RuntimeError("PostgreSQL cost governance repository is unavailable.")
        with get_postgres_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(cost_usd) FILTER (
                        WHERE tenant_id = %s
                    ), 0) AS tenant_cost,
                    COALESCE(SUM(cost_usd) FILTER (
                        WHERE tenant_id = %s AND session_id = %s
                    ), 0) AS session_cost,
                    COALESCE(SUM(cost_usd) FILTER (
                        WHERE tenant_id = %s AND user_id = NULLIF(%s, '')
                    ), 0) AS customer_cost
                FROM resource_usage_events
                WHERE created_at >= %s
                  AND completed_at IS NOT NULL
                """,
                (
                    tenant_id,
                    tenant_id, session_id,
                    tenant_id, user_id or "",
                    month_start,
                ),
            ).fetchone()
        return {
            "tenant_cost_usd": float(row["tenant_cost"] or 0),
            "session_cost_usd": float(row["session_cost"] or 0),
            "customer_cost_usd": float(row["customer_cost"] or 0),
        }

    def budget_for_tenant(
        self,
        tenant_id: str,
        *,
        default_budget_usd: float,
        default_warning_threshold: float,
    ) -> dict[str, Any]:
        if get_settings().database_provider != "postgres":
            return {
                "monthly_budget_usd": default_budget_usd,
                "warning_threshold": default_warning_threshold,
                "enabled": True,
                "source": "environment_default",
            }
        try:
            with get_postgres_connection() as conn:
                row = conn.execute(
                    """
                    SELECT monthly_budget_usd, warning_threshold, enabled
                    FROM tenant_ai_budgets
                    WHERE tenant_id = %s AND effective_from <= now()
                    """,
                    (tenant_id,),
                ).fetchone()
        except Exception:  # noqa: BLE001
            row = None
        if not row:
            return {
                "monthly_budget_usd": default_budget_usd,
                "warning_threshold": default_warning_threshold,
                "enabled": True,
                "source": "environment_default",
            }
        return {
            "monthly_budget_usd": float(row["monthly_budget_usd"]),
            "warning_threshold": float(row["warning_threshold"]),
            "enabled": bool(row["enabled"]),
            "source": "tenant_override",
        }
