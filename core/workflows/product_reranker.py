import re
from typing import Any

from core.workflows.product_search_query import ProductSearchQuery


def rerank_products(
    candidates: list[dict[str, Any]],
    structured_query: ProductSearchQuery,
    keyword_query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Rerank hybrid candidates into the final product list.

    The retriever supplies factual candidates. This deterministic reranker gives
    small boosts for exact lexical matches and captured soft preferences.
    """
    if not candidates:
        return []

    query_tokens = _tokens(keyword_query)
    soft_tokens = set(_tokens(" ".join(structured_query.soft_constraints or [])))
    reranked = []
    for index, candidate in enumerate(candidates):
        row = dict(candidate)
        searchable_text = " ".join(
            str(row.get(key, ""))
            for key in ("name", "category", "country", "brand", "embedding_source_text")
        )
        product_tokens = set(_tokens(searchable_text))

        lexical_overlap = _overlap_ratio(query_tokens, product_tokens)
        soft_overlap = _overlap_ratio(list(soft_tokens), product_tokens)
        hybrid_score = _as_float(row.get("hybrid_score"))
        keyword_score = _as_float(row.get("keyword_score"))
        vector_similarity = _as_float(row.get("vector_similarity", row.get("similarity")))

        rerank_score = (
            (0.55 * hybrid_score)
            + (0.2 * lexical_overlap)
            + (0.15 * soft_overlap)
            + (0.05 * keyword_score)
            + (0.05 * vector_similarity)
        )
        row["rerank_score"] = round(rerank_score, 6)
        row["lexical_overlap"] = round(lexical_overlap, 6)
        reranked.append((row["rerank_score"], -index, row))

    reranked.sort(reverse=True)
    return [row for _, _, row in reranked[:limit]]


def _tokens(text: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "di",
        "find",
        "for",
        "in",
        "me",
        "of",
        "product",
        "products",
        "rp",
        "show",
        "the",
        "to",
        "under",
    }
    tokens = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", text.lower()):
        if token not in stopwords and token not in tokens:
            tokens.append(token)
    return tokens


def _overlap_ratio(query_tokens: list[str], product_tokens: set[str]) -> float:
    if not query_tokens:
        return 0
    matches = sum(1 for token in query_tokens if token in product_tokens)
    return matches / len(query_tokens)


def _as_float(value: Any) -> float:
    if value is None:
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0
