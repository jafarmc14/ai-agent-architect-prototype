import re
from typing import Any

from configs import get_settings
from core.embeddings import build_product_embedding_text
from core.repositories.postgres_connection import get_postgres_connection


class PostgresProductEmbeddingRepository:
    """PostgreSQL pgvector storage for product embeddings."""

    def list_embedding_sources(self, only_missing: bool = False) -> list[dict[str, Any]]:
        conditions = ["p.is_active = true"]
        if only_missing:
            conditions.append("p.embedding_vector IS NULL")
        where_clause = " AND ".join(conditions)

        with get_postgres_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    p.id,
                    p.name,
                    p.description,
                    p.category,
                    p.brand,
                    p.country_of_origin,
                    p.embedding_source_text,
                    COALESCE(jsonb_agg(DISTINCT pv.name) FILTER (WHERE pv.id IS NOT NULL), '[]'::jsonb) AS variant_names,
                    COALESCE(jsonb_agg(DISTINCT pv.attributes) FILTER (WHERE pv.id IS NOT NULL), '[]'::jsonb) AS variant_attributes
                FROM products p
                LEFT JOIN product_variants pv ON pv.product_id = p.id AND pv.is_active = true
                WHERE {where_clause}
                GROUP BY p.id
                ORDER BY p.name
                """
            ).fetchall()

        return [
            {
                **dict(row),
                "embedding_text": build_product_embedding_text(dict(row)),
            }
            for row in rows
        ]

    def upsert_product_embedding(
        self,
        product_id: str,
        embedding: list[float],
        source_text: str,
        embedding_model: str | None = None,
    ) -> None:
        settings = get_settings()
        if len(embedding) != settings.vector_dimension:
            raise ValueError(
                f"Embedding dimension mismatch. Expected {settings.vector_dimension}, got {len(embedding)}."
            )

        embedding_literal = self._embedding_literal(embedding)
        with get_postgres_connection() as conn:
            conn.execute(
                """
                UPDATE products
                SET embedding_vector = %s::vector,
                    embedding_model = %s,
                    embedding_dimensions = %s,
                    embedding_source_text = %s,
                    embedding_updated_at = now(),
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    embedding_literal,
                    embedding_model or settings.embedding_model,
                    len(embedding),
                    source_text,
                    product_id,
                ),
            )

    def search_products_by_embedding(
        self,
        query_embedding: list[float],
        limit: int = 5,
        embedding_model: str | None = None,
        keyword_query: str = "",
        category: str = "",
        max_price: float = 0,
        min_price: float = 0,
        size: int | None = None,
        sku: str = "",
        available: bool | None = None,
        min_stock: int = 0,
    ) -> list[dict[str, Any]]:
        conditions = [
            "p.is_active = true",
            "p.embedding_vector IS NOT NULL",
            "(%s::text IS NULL OR p.embedding_model = %s)",
        ]
        params: list[Any] = [embedding_model, embedding_model]

        if category:
            conditions.append("p.category ILIKE %s")
            params.append(f"%{category}%")
        if min_price > 0:
            conditions.append("p.base_price >= %s")
            params.append(min_price)
        if max_price > 0:
            conditions.append("p.base_price <= %s")
            params.append(max_price)
        if size is not None:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM product_variants pv
                    WHERE pv.product_id = p.id
                      AND pv.is_active = true
                      AND pv.attributes ->> 'size' = %s
                )
                """
            )
            params.append(str(size))
        if sku:
            conditions.append(
                """
                (
                    p.sku ILIKE %s
                    OR EXISTS (
                        SELECT 1
                        FROM product_variants pv
                        WHERE pv.product_id = p.id
                          AND pv.sku ILIKE %s
                    )
                )
                """
            )
            params.extend((sku, sku))
        if available is True:
            conditions.append("COALESCE(ps.available_stock, 0) > 0")
        elif available is False:
            conditions.append("COALESCE(ps.available_stock, 0) = 0")
        if min_stock > 0:
            conditions.append("COALESCE(ps.available_stock, 0) >= %s")
            params.append(min_stock)

        where_clause = " AND ".join(conditions)
        embedding_literal = self._embedding_literal(query_embedding)
        keyword_tsquery = self._keyword_tsquery(keyword_query)
        vector_weight = 0.7
        keyword_weight = 0.3
        with get_postgres_connection() as conn:
            rows = conn.execute(
                f"""
                WITH product_stock AS (
                    SELECT
                        product_id,
                        COALESCE(SUM(quantity_on_hand - quantity_reserved), 0)::int AS available_stock
                    FROM inventory
                    GROUP BY product_id
                ),
                scored_products AS (
                    SELECT
                        p.name,
                        p.category,
                        p.base_price AS price,
                        COALESCE(ps.available_stock, 0)::int AS stock,
                        p.country_of_origin AS country,
                        1 - (p.embedding_vector <=> %s::vector) AS vector_similarity,
                        CASE
                            WHEN %s::text = '' THEN 0
                            ELSE ts_rank_cd(
                                to_tsvector(
                                    'simple',
                                    COALESCE(p.name, '') || ' ' ||
                                    COALESCE(p.description, '') || ' ' ||
                                    COALESCE(p.category, '') || ' ' ||
                                    COALESCE(p.brand, '') || ' ' ||
                                    COALESCE(p.country_of_origin, '') || ' ' ||
                                    COALESCE(p.embedding_source_text, '')
                                ),
                                to_tsquery('simple', %s)
                            )
                        END AS keyword_score,
                        p.embedding_vector <=> %s::vector AS vector_distance
                    FROM products p
                    LEFT JOIN product_stock ps ON ps.product_id = p.id
                    WHERE {where_clause}
                )
                SELECT
                    name,
                    category,
                    price,
                    stock,
                    country,
                    vector_similarity,
                    keyword_score,
                    ((%s * vector_similarity) + (%s * keyword_score)) AS hybrid_score
                FROM scored_products
                ORDER BY hybrid_score DESC, vector_distance ASC
                LIMIT %s
                """,
                (
                    embedding_literal,
                    keyword_tsquery,
                    keyword_tsquery,
                    embedding_literal,
                    *params,
                    vector_weight,
                    keyword_weight,
                    limit,
                ),
            ).fetchall()

        return [dict(row) for row in rows]

    def catalog_version(self) -> str:
        """Version key for cache invalidation after catalog or embedding changes."""
        with get_postgres_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*), COALESCE(MAX(updated_at)::text, ''),
                       COALESCE(MAX(embedding_updated_at)::text, '')
                FROM products
                WHERE is_active = true
                """
            ).fetchone()
        return ":".join(str(value or "") for value in row)

    @staticmethod
    def _embedding_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in embedding) + "]"

    @staticmethod
    def _keyword_tsquery(keyword_query: str) -> str:
        stopwords = {
            "a",
            "an",
            "and",
            "at",
            "bawah",
            "by",
            "cari",
            "di",
            "find",
            "for",
            "from",
            "give",
            "in",
            "list",
            "me",
            "of",
            "produk",
            "product",
            "products",
            "rp",
            "show",
            "the",
            "to",
            "under",
            "yang",
        }
        tokens = []
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", keyword_query.lower()):
            if token not in stopwords and token not in tokens:
                tokens.append(token)
        return " | ".join(tokens)
