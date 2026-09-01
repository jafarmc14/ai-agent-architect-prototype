import re
from typing import Any

from .token_accounting import estimate_tokens


def deduplicate_texts(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(value.strip())
    return unique


def compress_context(text: str, token_limit: int, query: str = "") -> str:
    if token_limit <= 0 or not text:
        return ""
    if estimate_tokens(text) <= token_limit:
        return text.strip()

    query_terms = _terms(query)
    units = deduplicate_texts([
        unit.strip()
        for unit in re.split(r"(?<=[.!?])\s+|\n+", text)
        if unit.strip()
    ])
    ranked = sorted(
        enumerate(units),
        key=lambda item: (_overlap(query_terms, item[1]), -item[0]),
        reverse=True,
    )
    selected = []
    used = 0
    for _, unit in ranked:
        unit_tokens = estimate_tokens(unit)
        if used + unit_tokens > token_limit:
            continue
        selected.append(unit)
        used += unit_tokens
    selected_set = set(selected)
    ordered = [unit for unit in units if unit in selected_set]
    return "\n".join(ordered).strip()


def select_relevant_messages(rows: list[dict[str, Any]], query: str, limit: int = 6) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    rows = list(rows)[-max(limit * 3, limit):]
    query_terms = _terms(query)
    scored = []
    for index, row in enumerate(rows):
        content = str(row.get("content", ""))
        relevance = _overlap(query_terms, content)
        recency = (index + 1) / max(len(rows), 1)
        scored.append(((2 * relevance) + recency, index, row))
    selected = sorted(scored, reverse=True)[:limit]
    selected_indexes = {index for _, index, _ in selected}
    return [row for index, row in enumerate(rows) if index in selected_indexes]


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(token) > 2
    }


def _overlap(query_terms: set[str], text: str) -> float:
    if not query_terms:
        return 0.0
    terms = _terms(text)
    return len(query_terms & terms) / len(query_terms)
