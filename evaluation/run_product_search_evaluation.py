import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "datasets" / "product_search.jsonl"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.privacy import redact_for_logs  # noqa: E402


TARGETS = {
    "precision_at_5": 0.90,
    "recall_at_10": 0.95,
    "ndcg_at_10": 0.85,
    "hard_constraint_satisfaction": 0.99,
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            case["line_number"] = line_number
            cases.append(case)
    return cases


def precision_at_k(ranked_names: list[str], relevant_names: set[str], k: int) -> float:
    if not ranked_names:
        return 1.0 if not relevant_names else 0.0
    top_k = ranked_names[:k]
    hits = sum(1 for name in top_k if name in relevant_names)
    return hits / len(top_k)


def recall_at_k(ranked_names: list[str], relevant_names: set[str], k: int) -> float:
    if not relevant_names:
        return 1.0
    top_k = ranked_names[:k]
    hits = sum(1 for name in top_k if name in relevant_names)
    return hits / len(relevant_names)


def ndcg_at_k(ranked_names: list[str], relevance_by_name: dict[str, int], k: int) -> float:
    if not relevance_by_name:
        return 1.0

    def dcg(gains: list[int]) -> float:
        return sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))

    actual_gains = [relevance_by_name.get(name, 0) for name in ranked_names[:k]]
    ideal_gains = sorted(relevance_by_name.values(), reverse=True)[:k]
    ideal = dcg(ideal_gains)
    if ideal == 0:
        return 1.0
    return dcg(actual_gains) / ideal


def hard_constraints_satisfied(row: dict[str, Any], constraints: dict[str, Any]) -> bool:
    if not constraints:
        return True

    category = constraints.get("category")
    if category and category.lower() not in str(row.get("category", "")).lower():
        return False

    price = float(row.get("price") or 0)
    min_price = float(constraints.get("min_price") or 0)
    max_price = float(constraints.get("max_price") or 0)
    if min_price > 0 and price < min_price:
        return False
    if max_price > 0 and price > max_price:
        return False

    stock = int(row.get("stock") or 0)
    if constraints.get("available") is True and stock <= 0:
        return False
    if constraints.get("available") is False and stock != 0:
        return False
    min_stock = int(constraints.get("min_stock") or 0)
    if min_stock > 0 and stock < min_stock:
        return False

    # Size/SKU are enforced in SQL. If a row is returned, the repository has
    # already applied them against product_variants/products.
    return True


def evaluate_case(case: dict[str, Any], *, deterministic_only: bool = False) -> dict[str, Any]:
    from configs import get_settings
    from core.embeddings import OpenAICompatibleEmbeddingProvider
    from core.repositories import ProductRepository
    from core.repositories.postgres_product_embedding_repository import PostgresProductEmbeddingRepository
    from core.workflows.product_reranker import rerank_products
    from core.workflows.product_search_query import extract_product_search_query

    settings = get_settings()
    query_input = case.get("input", {})
    structured_query = extract_product_search_query(**query_input)
    filter_category = structured_query.catalog_category or structured_query.category
    semantic_query_text = _semantic_query_text(structured_query)
    keyword_query = _keyword_query_text(structured_query)

    start = time.perf_counter()
    retrieval_mode = "deterministic"
    candidates = []
    final_rows = []
    exception = None

    try:
        if not deterministic_only and settings.database_provider == "postgres" and semantic_query_text:
            embedding = OpenAICompatibleEmbeddingProvider().embed_text(semantic_query_text)
            candidates = PostgresProductEmbeddingRepository().search_products_by_embedding(
                query_embedding=embedding,
                limit=20,
                embedding_model=settings.embedding_model,
                keyword_query=keyword_query,
                category=filter_category,
                max_price=structured_query.max_price,
                min_price=structured_query.min_price,
                size=structured_query.size,
                sku=structured_query.sku,
                available=structured_query.available,
                min_stock=structured_query.min_stock,
            )
            final_rows = rerank_products(candidates, structured_query, keyword_query, limit=10)
            retrieval_mode = "hybrid_reranked"

        if not final_rows:
            candidates = ProductRepository().find_products_by_filter(
                filter_category,
                structured_query.max_price,
                structured_query.min_price,
                size=structured_query.size,
                sku=structured_query.sku,
                available=structured_query.available,
                min_stock=structured_query.min_stock,
            )
            final_rows = [dict(row) for row in candidates[:10]]
            retrieval_mode = "deterministic"
    except Exception as exc:  # noqa: BLE001 - report evaluation failures without hiding the case.
        exception = redact_for_logs(repr(exc))

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    ranked_names = [row["name"] for row in final_rows]
    relevant_names = set(case.get("relevant_products", []))
    relevance_by_name = {
        name: int(score)
        for name, score in case.get("graded_relevance", {}).items()
    } or {name: 1 for name in relevant_names}

    top10_constraint_checks = [
        hard_constraints_satisfied(row, case.get("hard_constraints", {}))
        for row in final_rows[:10]
    ]
    hard_constraint_rate = (
        sum(1 for passed in top10_constraint_checks if passed) / len(top10_constraint_checks)
        if top10_constraint_checks
        else 1.0
    )

    return {
        "id": case["id"],
        "query": redact_for_logs(case["query"]),
        "retrieval_mode": retrieval_mode,
        "expected_relevant": list(relevant_names),
        "ranked_products": ranked_names,
        "top5": ranked_names[:5],
        "candidate_count": len(candidates),
        "result_count": len(final_rows),
        "precision_at_5": round(precision_at_k(ranked_names, relevant_names, 5), 4),
        "recall_at_10": round(recall_at_k(ranked_names, relevant_names, 10), 4),
        "ndcg_at_10": round(ndcg_at_k(ranked_names, relevance_by_name, 10), 4),
        "hard_constraint_satisfaction": round(hard_constraint_rate, 4),
        "hard_constraints": case.get("hard_constraints", {}),
        "exception": exception,
        "latency_ms": latency_ms,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [result for result in results if result["exception"] is None]

    def average(key: str) -> float:
        if not evaluated:
            return 0
        return round(sum(result[key] for result in evaluated) / len(evaluated), 4)

    summary = {
        "total_cases": len(results),
        "evaluated_cases": len(evaluated),
        "exceptions": sum(1 for result in results if result["exception"]),
        "precision_at_5": average("precision_at_5"),
        "recall_at_10": average("recall_at_10"),
        "ndcg_at_10": average("ndcg_at_10"),
        "hard_constraint_satisfaction": average("hard_constraint_satisfaction"),
        "avg_latency_ms": (
            round(sum(result["latency_ms"] for result in evaluated) / len(evaluated), 2)
            if evaluated
            else 0
        ),
    }
    summary["targets"] = TARGETS
    summary["target_pass"] = {
        metric: summary[metric] >= target
        for metric, target in TARGETS.items()
    }
    summary["all_targets_pass"] = all(summary["target_pass"].values()) and summary["exceptions"] == 0
    return summary


def _semantic_query_text(structured_query) -> str:
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


def _keyword_query_text(structured_query) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run product search evaluation.")
    parser.add_argument("--dataset", default=str(DATASET_PATH))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="Skip embedding/vector retrieval and evaluate database filters plus deterministic ranking only.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(dataset_path)
    if args.limit > 0:
        cases = cases[: args.limit]

    from configs import get_settings

    settings = get_settings()
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']} - {case['query']}")
        results.append(evaluate_case(case, deterministic_only=args.deterministic_only))

    report = {
        "name": "product_search_report_v1",
        "created_at": datetime.now().isoformat(),
        "database_provider": settings.database_provider,
        "embedding_model": settings.embedding_model,
        "deterministic_only": args.deterministic_only,
        "dataset": str(dataset_path),
        "summary": summarize(results),
        "results": results,
    }

    latest_path = report_dir / "product_search_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("")
    print("Product search evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")
    return 0 if report["summary"]["all_targets_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
