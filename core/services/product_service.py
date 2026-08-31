from typing import Any

from configs import get_settings
from core.embeddings import OpenAICompatibleEmbeddingProvider
from core.repositories import ProductRepository
from core.repositories.postgres_product_embedding_repository import PostgresProductEmbeddingRepository
from core.structured_outputs import FilterOutput
from core.workflows.product_reranker import rerank_products
from core.workflows.product_search_query import ProductSearchQuery, extract_product_search_query


PRODUCT_ALIASES = {
    "nike shoes": "Nike",
    "nike shoe": "Nike",
    "sepatu nike": "Nike",
    "kaos hitam": "Black Plain T-Shirt",
    "kaos polos hitam": "Black Plain T-Shirt",
    "baju hitam": "Black Plain T-Shirt",
    "t-shirt hitam": "Black Plain T-Shirt",
    "tas eiger": "Eiger",
    "headphone sony": "Sony",
    "sony headphone": "Sony",
    "sony headphones": "Sony",
    "jam casio": "Casio",
}


def normalize_product_query(product_name: str) -> str:
    product_key = product_name.lower().strip()
    return PRODUCT_ALIASES.get(product_key, product_name)


class ProductService:
    """Business logic for product lookup and recommendations."""

    def __init__(
        self,
        repository: ProductRepository | None = None,
        semantic_repository: PostgresProductEmbeddingRepository | None = None,
        embedding_provider: OpenAICompatibleEmbeddingProvider | None = None,
        semantic_search_enabled: bool | None = None,
    ):
        self.repository = repository or ProductRepository()
        self.semantic_repository = semantic_repository
        self.embedding_provider = embedding_provider
        self.semantic_search_enabled = (
            get_settings().database_provider == "postgres"
            if semantic_search_enabled is None
            else semantic_search_enabled
        )

    def check_stock(self, product_name: str) -> str:
        search_term = normalize_product_query(product_name)
        rows = self.repository.find_products_by_name(search_term)

        if not rows:
            return f"No products found matching '{product_name}' in the database."

        results = []
        for row in rows:
            results.append(self._format_product_row(row))
        return "\n".join(results)

    def search_products(
        self,
        category: str = "",
        max_price: float = 0,
        min_price: float = 0,
        query: str = "",
        size: int | None = None,
        color: str = "",
        waterproof: bool | None = None,
        sku: str = "",
        available: bool | None = None,
        min_stock: int = 0,
        soft_preferences: str = "",
    ) -> str:
        structured_query = extract_product_search_query(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            size=size,
            color=color,
            waterproof=waterproof,
            sku=sku,
            available=available,
            min_stock=min_stock,
            soft_preferences=soft_preferences,
        )
        FilterOutput(**structured_query.to_dict())
        filter_category = structured_query.catalog_category or structured_query.category
        semantic_note = ""
        semantic_query_text = self._semantic_query_text(structured_query)
        rows = self._hybrid_search(structured_query, filter_category, semantic_query_text)
        if rows:
            semantic_note = "Hybrid retrieval + reranker: enabled. Retrieved top 20 candidates, reranked to top 5."
        else:
            rows = self.repository.find_products_by_filter(
                filter_category,
                structured_query.max_price,
                structured_query.min_price,
                size=structured_query.size,
                sku=structured_query.sku,
                available=structured_query.available,
                min_stock=structured_query.min_stock,
            )
            if self.semantic_search_enabled and semantic_query_text:
                semantic_note = "Hybrid retrieval had no embedded matches; used deterministic filters."

        if not rows:
            filters = []
            if structured_query.category:
                filters.append(f"category='{structured_query.category}'")
            if structured_query.min_price > 0:
                filters.append(f"min_price=Rp{structured_query.min_price:,.0f}")
            if structured_query.max_price > 0:
                filters.append(f"max_price=Rp{structured_query.max_price:,.0f}")
            if structured_query.sku:
                filters.append(f"sku='{structured_query.sku}'")
            if structured_query.available is not None:
                filters.append(f"available={structured_query.available}")
            if structured_query.min_stock > 0:
                filters.append(f"min_stock={structured_query.min_stock}")
            return f"No products found matching filters: {', '.join(filters)}."

        results = [f"Found {len(rows)} product(s):"]
        if semantic_note:
            results.append(semantic_note)
        if structured_query.hard_constraints:
            results.append(f"Applied hard constraints: {structured_query.hard_constraints}")
        if structured_query.soft_constraints:
            results.append(f"Captured soft preferences: {', '.join(structured_query.soft_constraints)}")
        unsupported_hard_constraints = structured_query.unsupported_hard_constraints()
        if unsupported_hard_constraints:
            results.append(
                "Hard constraints captured but not yet filterable in the catalog: "
                + ", ".join(unsupported_hard_constraints)
                + "."
            )
        unsupported_filters = structured_query.unsupported_filters()
        if unsupported_filters:
            results.append(
                "Structured criteria captured but not yet filterable in the catalog: "
                + ", ".join(unsupported_filters)
                + "."
            )
        for row in rows:
            results.append(self._format_product_row(row))
        return "\n".join(results)

    def _hybrid_search(
        self,
        structured_query: ProductSearchQuery,
        filter_category: str,
        semantic_query_text: str,
    ) -> list[dict[str, Any]]:
        if not self.semantic_search_enabled or not semantic_query_text:
            return []

        try:
            embedding_provider = self.embedding_provider or OpenAICompatibleEmbeddingProvider()
            semantic_repository = self.semantic_repository or PostgresProductEmbeddingRepository()
            query_embedding = embedding_provider.embed_text(semantic_query_text)
            keyword_query = self._keyword_query_text(structured_query)
            candidates = semantic_repository.search_products_by_embedding(
                query_embedding=query_embedding,
                limit=20,
                embedding_model=get_settings().embedding_model,
                keyword_query=keyword_query,
                category=filter_category,
                max_price=structured_query.max_price,
                min_price=structured_query.min_price,
                size=structured_query.size,
                sku=structured_query.sku,
                available=structured_query.available,
                min_stock=structured_query.min_stock,
            )
            return rerank_products(candidates, structured_query, keyword_query, limit=5)
        except (RuntimeError, ValueError, OSError):
            return []

    def _semantic_query_text(self, structured_query: ProductSearchQuery) -> str:
        parts = []
        if structured_query.query:
            parts.append(structured_query.query)
        if structured_query.soft_constraints:
            parts.extend(structured_query.soft_constraints)
        if structured_query.color:
            parts.append(f"color {structured_query.color}")
        if structured_query.waterproof is True:
            parts.append("waterproof")
        elif structured_query.waterproof is False:
            parts.append("not waterproof")
        return " ".join(dict.fromkeys(part.strip() for part in parts if part.strip()))

    def _keyword_query_text(self, structured_query: ProductSearchQuery) -> str:
        parts = []
        if structured_query.query:
            parts.append(structured_query.query)
        if structured_query.category:
            parts.append(structured_query.category)
        if structured_query.catalog_category:
            parts.append(structured_query.catalog_category)
        if structured_query.soft_constraints:
            parts.extend(structured_query.soft_constraints)
        if structured_query.color:
            parts.append(structured_query.color)
        if structured_query.waterproof is True:
            parts.append("waterproof")
        elif structured_query.waterproof is False:
            parts.append("not waterproof")
        return " ".join(dict.fromkeys(part.strip() for part in parts if part.strip()))

    def _format_product_row(self, row) -> str:
        scores = []
        try:
            hybrid_score = row["hybrid_score"]
        except (KeyError, IndexError):
            hybrid_score = None
        if hybrid_score is not None:
            scores.append(f"Hybrid: {float(hybrid_score):.3f}")
        try:
            rerank_score = row["rerank_score"]
        except (KeyError, IndexError):
            rerank_score = None
        if rerank_score is not None:
            scores.insert(0, f"Rerank: {float(rerank_score):.3f}")
        try:
            keyword_score = row["keyword_score"]
        except (KeyError, IndexError):
            keyword_score = None
        if keyword_score is not None:
            scores.append(f"Keyword: {float(keyword_score):.3f}")
        try:
            vector_similarity = row["vector_similarity"]
        except (KeyError, IndexError):
            vector_similarity = None
        if vector_similarity is None:
            try:
                vector_similarity = row["similarity"]
            except (KeyError, IndexError):
                vector_similarity = None
        if vector_similarity is not None:
            scores.append(f"Vector: {float(vector_similarity):.3f}")
        score_text = f" | Scores: {', '.join(scores)}" if scores else ""
        return (
            f"- {row['name']} | Category: {row['category']} | Price: Rp{row['price']:,.0f} "
            f"| Stock: {row['stock']} units | Origin: {row['country']}{score_text}"
        )


product_service = ProductService()
