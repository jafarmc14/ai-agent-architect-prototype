from typing import Any

from configs import get_settings


class PostgresVectorRepository:
    """PostgreSQL pgvector storage for knowledge document chunks."""

    def __init__(self, database_url: str | None = None):
        self.settings = get_settings()
        self.database_url = database_url or self.settings.postgres_database_url

    def upsert_document(
        self,
        title: str,
        source: str,
        source_type: str = "text",
        version: str | None = None,
        language: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        psycopg = self._import_psycopg()
        with psycopg.connect(self._required_database_url()) as conn:
            row = conn.execute(
                """
                INSERT INTO documents (title, source, source_type, version, language, metadata)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    title,
                    source,
                    source_type,
                    version,
                    language,
                    psycopg.types.json.Jsonb(metadata or {}),
                ),
            ).fetchone()
            return str(row[0])

    def upsert_chunk(
        self,
        document_id: str,
        chunk_index: int,
        content: str,
        embedding: list[float],
        token_count: int | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_model: str | None = None,
    ) -> str:
        psycopg = self._import_psycopg()
        embedding_literal = self._embedding_literal(embedding)
        with psycopg.connect(self._required_database_url()) as conn:
            row = conn.execute(
                """
                INSERT INTO document_chunks (
                    document_id,
                    chunk_index,
                    content,
                    token_count,
                    embedding_vector,
                    embedding_model,
                    embedding_dimensions,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s::jsonb)
                ON CONFLICT (document_id, chunk_index) DO UPDATE SET
                    content = EXCLUDED.content,
                    token_count = EXCLUDED.token_count,
                    embedding_vector = EXCLUDED.embedding_vector,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_dimensions = EXCLUDED.embedding_dimensions,
                    metadata = EXCLUDED.metadata
                RETURNING id
                """,
                (
                    document_id,
                    chunk_index,
                    content,
                    token_count,
                    embedding_literal,
                    embedding_model or self.settings.embedding_model,
                    len(embedding),
                    psycopg.types.json.Jsonb(metadata or {}),
                ),
            ).fetchone()
            return str(row[0])

    def search_chunks(
        self,
        query_embedding: list[float],
        limit: int = 5,
        embedding_model: str | None = None,
    ) -> list[dict[str, Any]]:
        psycopg = self._import_psycopg()
        embedding_literal = self._embedding_literal(query_embedding)
        with psycopg.connect(self._required_database_url()) as conn:
            rows = conn.execute(
                """
                SELECT
                    dc.id,
                    dc.document_id,
                    d.title,
                    d.source,
                    dc.chunk_index,
                    dc.content,
                    dc.embedding_model,
                    1 - (dc.embedding_vector <=> %s::vector) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE dc.embedding_vector IS NOT NULL
                  AND (%s IS NULL OR dc.embedding_model = %s)
                ORDER BY dc.embedding_vector <=> %s::vector
                LIMIT %s
                """,
                (
                    embedding_literal,
                    embedding_model,
                    embedding_model,
                    embedding_literal,
                    limit,
                ),
            ).fetchall()

        return [
            {
                "id": str(row[0]),
                "document_id": str(row[1]),
                "title": row[2],
                "source": row[3],
                "chunk_index": row[4],
                "content": row[5],
                "embedding_model": row[6],
                "similarity": float(row[7]),
            }
            for row in rows
        ]

    def _required_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required for PostgreSQL vector storage.")
        return self.database_url

    @staticmethod
    def _embedding_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in embedding) + "]"

    @staticmethod
    def _import_psycopg():
        try:
            import psycopg
            import psycopg.types.json
        except ImportError as exc:
            raise RuntimeError(
                "Missing PostgreSQL driver. Install it with: py -m pip install psycopg[binary]"
            ) from exc
        return psycopg
