from typing import Any

from configs import get_settings
from core.repositories.postgres_connection import get_postgres_connection


_MEMORY_CONVERSATIONS: dict[str, dict[str, Any]] = {}
_MEMORY_MESSAGES: dict[str, list[dict[str, Any]]] = {}


class ConversationRepository:
    """Conversation transcript and structured state storage."""

    def get_or_create_conversation(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        tenant_id: str = "default",
        channel: str = "streamlit",
    ) -> dict[str, Any]:
        if get_settings().database_provider != "postgres":
            return self._memory_conversation(session_id, user_id, tenant_id, channel)

        import psycopg.types.json

        with get_postgres_connection() as conn:
            existing = conn.execute(
                """
                SELECT id, session_id, user_id, tenant_id, structured_state, metadata
                FROM conversations
                WHERE tenant_id = %s
                  AND session_id = %s
                  AND (%s::uuid IS NULL OR user_id = %s::uuid)
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (tenant_id, session_id, user_id, user_id),
            ).fetchone()
            if existing:
                return dict(existing)

            row = conn.execute(
                """
                INSERT INTO conversations (user_id, session_id, channel, tenant_id, structured_state, metadata)
                VALUES (%s::uuid, %s, %s, %s, '{}'::jsonb, %s::jsonb)
                RETURNING id, session_id, user_id, tenant_id, structured_state, metadata
                """,
                (user_id, session_id, channel, tenant_id, psycopg.types.json.Jsonb({"source": "ai_agent_runtime"})),
            ).fetchone()
            return dict(row)

    def append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        tenant_id: str = "default",
        metadata: dict[str, Any] | None = None,
        tool_name: str = "",
        tool_arguments: dict[str, Any] | None = None,
        tool_output: dict[str, Any] | None = None,
    ) -> None:
        if get_settings().database_provider != "postgres":
            _MEMORY_MESSAGES.setdefault(conversation_id, []).append(
                {
                    "role": role,
                    "content": content,
                    "metadata": metadata or {},
                    "tool_name": tool_name,
                    "tool_arguments": tool_arguments,
                    "tool_output": tool_output,
                }
            )
            return

        import psycopg.types.json

        with get_postgres_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, role, content, tool_name, tool_arguments, tool_output, tenant_id, metadata
                )
                VALUES (%s, %s::message_role, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb)
                """,
                (
                    conversation_id,
                    role,
                    content,
                    tool_name or None,
                    psycopg.types.json.Jsonb(tool_arguments or {}),
                    psycopg.types.json.Jsonb(tool_output or {}),
                    tenant_id,
                    psycopg.types.json.Jsonb(metadata or {}),
                ),
            )

    def recent_messages(self, *, conversation_id: str, limit: int = 6) -> list[dict[str, Any]]:
        if get_settings().database_provider != "postgres":
            return list(_MEMORY_MESSAGES.get(conversation_id, []))[-limit:]

        with get_postgres_connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content, metadata, created_at
                FROM messages
                WHERE conversation_id = %s
                  AND role IN ('user', 'assistant')
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (conversation_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_structured_state(self, *, conversation_id: str) -> dict[str, Any]:
        if get_settings().database_provider != "postgres":
            return dict(_MEMORY_CONVERSATIONS.get(conversation_id, {}).get("structured_state", {}))

        with get_postgres_connection() as conn:
            row = conn.execute(
                "SELECT structured_state FROM conversations WHERE id = %s",
                (conversation_id,),
            ).fetchone()
        return dict(row["structured_state"] or {}) if row else {}

    def update_structured_state(self, *, conversation_id: str, structured_state: dict[str, Any]) -> None:
        if get_settings().database_provider != "postgres":
            _MEMORY_CONVERSATIONS.setdefault(conversation_id, {})["structured_state"] = structured_state
            return

        import psycopg.types.json

        with get_postgres_connection() as conn:
            conn.execute(
                """
                UPDATE conversations
                SET structured_state = %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                """,
                (psycopg.types.json.Jsonb(structured_state), conversation_id),
            )

    def reset_memory(self) -> None:
        _MEMORY_CONVERSATIONS.clear()
        _MEMORY_MESSAGES.clear()

    @staticmethod
    def _memory_conversation(session_id: str, user_id: str | None, tenant_id: str, channel: str) -> dict[str, Any]:
        conversation_id = f"{tenant_id}:{user_id or session_id}"
        conversation = _MEMORY_CONVERSATIONS.setdefault(
            conversation_id,
            {
                "id": conversation_id,
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "channel": channel,
                "structured_state": {},
                "metadata": {"source": "memory_fallback"},
            },
        )
        return dict(conversation)
