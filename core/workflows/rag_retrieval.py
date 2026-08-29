from dataclasses import dataclass
import re
from typing import Any


TRUST_LEVELS = {
    "OFFICIAL": 1.0,
    "INTERNAL_APPROVED": 0.9,
    "INTERNAL_DRAFT": 0.55,
    "USER_GENERATED": 0.35,
    "EXTERNAL": 0.25,
}


@dataclass(frozen=True)
class RetrievalScope:
    tenant_id: str = "default"
    role: str = "customer"
    department: str = "public"
    access_level: str = "public"


@dataclass(frozen=True)
class RetrievalResult:
    answer_context: str
    chunks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    abstained: bool
    reason: str | None = None


def rerank_rag_chunks(chunks: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    reranked = []
    for index, chunk in enumerate(chunks):
        row = dict(chunk)
        metadata = row.get("document_metadata") or {}
        trust_level = str(metadata.get("trust_level", "EXTERNAL")).upper()
        trust_weight = TRUST_LEVELS.get(trust_level, TRUST_LEVELS["EXTERNAL"])
        similarity = float(row.get("similarity") or 0)
        row["trust_level"] = trust_level
        row["trust_weight"] = trust_weight
        row["rerank_score"] = round((0.75 * similarity) + (0.25 * trust_weight), 6)
        reranked.append((row["rerank_score"], -index, row))

    reranked.sort(reverse=True)
    return [row for _, _, row in reranked[:limit]]


def build_rag_context(
    chunks: list[dict[str, Any]],
    query: str = "",
    min_similarity: float = 0.45,
    min_query_overlap: float = 0.5,
) -> RetrievalResult:
    if not chunks:
        return RetrievalResult(
            answer_context="",
            chunks=[],
            citations=[],
            abstained=True,
            reason="No authorized fresh evidence was retrieved.",
        )

    query_terms = _query_terms(query)
    strong_chunks = []
    for chunk in chunks:
        if float(chunk.get("similarity") or 0) < min_similarity:
            continue
        if query_terms and _overlap_ratio(query_terms, chunk.get("content", "")) < min_query_overlap:
            continue
        strong_chunks.append(chunk)
    if not strong_chunks:
        return RetrievalResult(
            answer_context="",
            chunks=chunks,
            citations=[],
            abstained=True,
            reason="Retrieved evidence is below the minimum similarity threshold.",
        )

    context_parts = []
    citations = []
    for index, chunk in enumerate(strong_chunks, start=1):
        metadata = chunk.get("document_metadata") or {}
        citation_id = f"C{index}"
        citations.append(
            {
                "citation_id": citation_id,
                "document_id": metadata.get("document_id"),
                "title": chunk.get("title"),
                "source": chunk.get("source"),
                "version": metadata.get("version"),
                "effective_date": metadata.get("effective_date"),
                "trust_level": metadata.get("trust_level"),
                "chunk_index": chunk.get("chunk_index"),
                "similarity": round(float(chunk.get("similarity") or 0), 4),
            }
        )
        context_parts.append(
            f"[{citation_id}] {chunk.get('title')} "
            f"({metadata.get('document_id')}, version {metadata.get('version')}, "
            f"effective {metadata.get('effective_date')})\n{chunk.get('content')}"
        )

    return RetrievalResult(
        answer_context="\n\n".join(context_parts),
        chunks=strong_chunks,
        citations=citations,
        abstained=False,
    )


def _query_terms(query: str) -> set[str]:
    stopwords = {
        "about",
        "after",
        "and",
        "can",
        "does",
        "for",
        "how",
        "long",
        "take",
        "takes",
        "the",
        "what",
        "you",
        "your",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", query.lower())
        if len(token) > 2 and token not in stopwords
    }


def _overlap_ratio(query_terms: set[str], content: str) -> float:
    if not query_terms:
        return 0
    content_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9]+", content.lower()))
    return len(query_terms & content_terms) / len(query_terms)
