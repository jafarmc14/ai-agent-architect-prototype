from typing import Any

from configs import get_settings
from core.prompts.registry import PromptVersion
from core.repositories.postgres_connection import get_postgres_connection


class PromptRepository:
    """Stores prompt version metadata for audit and rollback."""

    def upsert_prompt_version(self, prompt: PromptVersion) -> None:
        if get_settings().database_provider != "postgres":
            return

        import psycopg.types.json

        with get_postgres_connection() as conn:
            conn.execute(
                """
                INSERT INTO prompt_versions (
                    prompt_id, version, content, status, evaluation_score,
                    previous_version, created_at, activated_at, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::timestamptz,
                        CASE WHEN %s = 'active' THEN now() ELSE NULL END,
                        %s::jsonb)
                ON CONFLICT (prompt_id, version) DO UPDATE
                SET content = EXCLUDED.content,
                    created_at = EXCLUDED.created_at,
                    status = EXCLUDED.status,
                    evaluation_score = EXCLUDED.evaluation_score,
                    previous_version = EXCLUDED.previous_version,
                    metadata = EXCLUDED.metadata
                """,
                (
                    prompt.prompt_id,
                    prompt.version,
                    prompt.content,
                    prompt.status,
                    prompt.evaluation_score,
                    prompt.previous_version or None,
                    prompt.created_at,
                    prompt.status,
                    psycopg.types.json.Jsonb(prompt.metadata()),
                ),
            )

    def activate_prompt_version(self, prompt_id: str, version: str) -> None:
        if get_settings().database_provider != "postgres":
            return

        with get_postgres_connection() as conn:
            conn.execute(
                """
                UPDATE prompt_versions
                SET status = 'archived',
                    archived_at = now()
                WHERE prompt_id = %s
                  AND status = 'active'
                  AND version <> %s
                """,
                (prompt_id, version),
            )
            conn.execute(
                """
                UPDATE prompt_versions
                SET status = 'active',
                    activated_at = now(),
                    archived_at = NULL
                WHERE prompt_id = %s
                  AND version = %s
                """,
                (prompt_id, version),
            )

    def list_prompt_metadata(self) -> list[dict[str, Any]]:
        if get_settings().database_provider != "postgres":
            return []

        with get_postgres_connection() as conn:
            rows = conn.execute(
                """
                SELECT prompt_id, version, status, evaluation_score, previous_version, created_at, metadata
                FROM prompt_versions
                ORDER BY prompt_id, created_at
                """
            ).fetchall()
        return [dict(row) for row in rows]
