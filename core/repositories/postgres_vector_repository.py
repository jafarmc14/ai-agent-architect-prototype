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
        tenant_id: str = "default",
        effective_date: str | None = None,
        expires_at: str | None = None,
        status: str = "active",
        superseded_by: str | None = None,
        approval_status: str = "uploaded",
    ) -> str:
        psycopg = self._import_psycopg()
        metadata = metadata or {}
        document_id = metadata.get("document_id")
        with psycopg.connect(self._required_database_url()) as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM documents
                WHERE tenant_id = %s
                  AND (
                      source = %s
                      OR (%s::text IS NOT NULL AND metadata->>'document_id' = %s)
                  )
                LIMIT 1
                """,
                (tenant_id, source, document_id, document_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE documents
                    SET title = %s,
                        source = %s,
                        source_type = %s,
                        version = %s,
                        language = %s,
                        metadata = %s::jsonb,
                        tenant_id = %s,
                        effective_date = %s,
                        expires_at = %s,
                        status = %s,
                        superseded_by = %s,
                        approval_status = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        title,
                        source,
                        source_type,
                        version,
                        language,
                        psycopg.types.json.Jsonb(metadata),
                        tenant_id,
                        effective_date,
                        expires_at,
                        status,
                        superseded_by,
                        approval_status,
                        existing[0],
                    ),
                )
                return str(existing[0])

            row = conn.execute(
                """
                INSERT INTO documents (
                    title,
                    source,
                    source_type,
                    version,
                    language,
                    metadata,
                    tenant_id,
                    effective_date,
                    expires_at,
                    status,
                    superseded_by,
                    approval_status
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    title,
                    source,
                    source_type,
                    version,
                    language,
                    psycopg.types.json.Jsonb(metadata),
                    tenant_id,
                    effective_date,
                    expires_at,
                    status,
                    superseded_by,
                    approval_status,
                ),
            ).fetchone()
            return str(row[0])

    def delete_document_chunks(self, document_id: str) -> int:
        psycopg = self._import_psycopg()
        with psycopg.connect(self._required_database_url()) as conn:
            result = conn.execute(
                "DELETE FROM document_chunks WHERE document_id = %s",
                (document_id,),
            )
            return result.rowcount or 0

    def upsert_chunk(
        self,
        document_id: str,
        chunk_index: int,
        content: str,
        embedding: list[float],
        token_count: int | None = None,
        metadata: dict[str, Any] | None = None,
        embedding_model: str | None = None,
        tenant_id: str = "default",
    ) -> str:
        psycopg = self._import_psycopg()
        if len(embedding) != self.settings.vector_dimension:
            raise ValueError(
                f"Embedding dimension mismatch. Expected {self.settings.vector_dimension}, got {len(embedding)}."
            )
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
                    metadata,
                    tenant_id
                )
                VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s::jsonb, %s)
                ON CONFLICT (document_id, chunk_index) DO UPDATE SET
                    content = EXCLUDED.content,
                    token_count = EXCLUDED.token_count,
                    embedding_vector = EXCLUDED.embedding_vector,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_dimensions = EXCLUDED.embedding_dimensions,
                    metadata = EXCLUDED.metadata,
                    tenant_id = EXCLUDED.tenant_id
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
                    tenant_id,
                ),
            ).fetchone()
            return str(row[0])

    def search_chunks(
        self,
        query_embedding: list[float],
        limit: int = 5,
        embedding_model: str | None = None,
        tenant_id: str = "default",
        role: str = "customer",
        department: str = "public",
        access_level: str = "public",
        status: str = "active",
        approval_status: str = "indexed",
        min_trust_level: str = "EXTERNAL",
    ) -> list[dict[str, Any]]:
        psycopg = self._import_psycopg()
        embedding_literal = self._embedding_literal(query_embedding)
        allowed_access_levels = self._allowed_access_levels(access_level)
        allowed_trust_levels = self._allowed_trust_levels(min_trust_level)
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
                    d.metadata AS document_metadata,
                    dc.metadata AS chunk_metadata,
                    d.tenant_id,
                    1 - (dc.embedding_vector <=> %s::vector) AS similarity,
                    CASE UPPER(COALESCE(d.metadata->>'trust_level', 'EXTERNAL'))
                        WHEN 'OFFICIAL' THEN 1.0
                        WHEN 'INTERNAL_APPROVED' THEN 0.9
                        WHEN 'INTERNAL_DRAFT' THEN 0.55
                        WHEN 'USER_GENERATED' THEN 0.35
                        ELSE 0.25
                    END AS trust_weight,
                    (
                        0.75 * (1 - (dc.embedding_vector <=> %s::vector))
                        + 0.25 * CASE UPPER(COALESCE(d.metadata->>'trust_level', 'EXTERNAL'))
                            WHEN 'OFFICIAL' THEN 1.0
                            WHEN 'INTERNAL_APPROVED' THEN 0.9
                            WHEN 'INTERNAL_DRAFT' THEN 0.55
                            WHEN 'USER_GENERATED' THEN 0.35
                            ELSE 0.25
                        END
                    ) AS retrieval_score
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE dc.embedding_vector IS NOT NULL
                  AND (%s::text IS NULL OR dc.embedding_model = %s)
                  AND d.tenant_id = %s
                  AND d.status = %s
                  AND COALESCE(d.approval_status, 'uploaded') = %s
                  AND (d.effective_date IS NULL OR d.effective_date <= CURRENT_DATE)
                  AND (d.expires_at IS NULL OR d.expires_at > CURRENT_DATE)
                  AND d.superseded_by IS NULL
                  AND COALESCE(d.metadata->>'access_level', 'public') = ANY(%s)
                  AND COALESCE(d.metadata->>'trust_level', 'EXTERNAL') = ANY(%s)
                  AND (
                      COALESCE(d.metadata->>'role', 'customer') IN ('any', %s)
                      OR COALESCE(d.metadata->>'access_level', 'public') = 'public'
                  )
                  AND (
                      COALESCE(d.metadata->>'department', 'public') IN ('any', 'public', %s)
                      OR COALESCE(d.metadata->>'access_level', 'public') = 'public'
                  )
                ORDER BY retrieval_score DESC, dc.embedding_vector <=> %s::vector
                LIMIT %s
                """,
                (
                    embedding_literal,
                    embedding_literal,
                    embedding_model,
                    embedding_model,
                    tenant_id,
                    status,
                    approval_status,
                    allowed_access_levels,
                    allowed_trust_levels,
                    role,
                    department,
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
                "document_metadata": row[7],
                "chunk_metadata": row[8],
                "tenant_id": row[9],
                "similarity": float(row[10]),
                "trust_weight": float(row[11]),
                "retrieval_score": float(row[12]),
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

    @staticmethod
    def _allowed_access_levels(access_level: str) -> list[str]:
        hierarchy = ["public", "internal", "restricted"]
        normalized = access_level.lower()
        if normalized not in hierarchy:
            normalized = "public"
        return hierarchy[: hierarchy.index(normalized) + 1]

    @staticmethod
    def _allowed_trust_levels(min_trust_level: str) -> list[str]:
        ordered = ["EXTERNAL", "USER_GENERATED", "INTERNAL_DRAFT", "INTERNAL_APPROVED", "OFFICIAL"]
        normalized = min_trust_level.upper()
        if normalized not in ordered:
            normalized = "EXTERNAL"
        return ordered[ordered.index(normalized) :]
