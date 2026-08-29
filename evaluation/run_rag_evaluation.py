import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "datasets" / "rag.jsonl"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    from configs import get_settings
    from core.embeddings import OpenAICompatibleEmbeddingProvider
    from core.repositories.postgres_vector_repository import PostgresVectorRepository
    from core.workflows import RetrievalScope, build_rag_context, rerank_rag_chunks

    settings = get_settings()
    start = time.perf_counter()
    exception = None
    chunks = []
    context = None
    try:
        embedding = OpenAICompatibleEmbeddingProvider().embed_text(case["query"])
        retrieved = PostgresVectorRepository().search_chunks(
            query_embedding=embedding,
            limit=12,
            embedding_model=settings.embedding_model,
            tenant_id="default",
            role="customer",
            department="public",
            access_level="public",
            status="active",
            min_trust_level="EXTERNAL",
        )
        chunks = rerank_rag_chunks(retrieved, limit=5)
        context = build_rag_context(chunks, query=case["query"])
    except Exception as exc:  # noqa: BLE001
        exception = repr(exc)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    relevant = set(case.get("relevant_documents", []))
    evidence_chunks = context.chunks if context and not context.abstained else []
    retrieved_doc_ids = [
        (chunk.get("document_metadata") or {}).get("document_id")
        for chunk in evidence_chunks
    ]
    retrieved_set = set(doc_id for doc_id in retrieved_doc_ids if doc_id)
    should_abstain = bool(case.get("should_abstain"))
    abstained = bool(context.abstained) if context else False
    citations = context.citations if context else []
    answer_context = context.answer_context if context else ""

    recall_at_5 = 1.0 if not relevant else len(relevant & retrieved_set) / len(relevant)
    precision_at_5 = 1.0 if not retrieved_doc_ids and not relevant else (
        len(relevant & retrieved_set) / len(retrieved_doc_ids) if retrieved_doc_ids else 0
    )
    required_terms = case.get("required_terms", [])
    completeness = _term_coverage(answer_context, required_terms)
    citation_doc_ids = {citation.get("document_id") for citation in citations}
    citation_correctness = 1.0 if should_abstain else (1.0 if relevant <= citation_doc_ids else 0.0)
    faithfulness = 1.0 if should_abstain else (1.0 if citations and completeness > 0 else 0.0)
    correct_abstention = 1.0 if abstained == should_abstain else 0.0
    freshness_correctness = 1.0 if all(_is_fresh(chunk) for chunk in evidence_chunks) else 0.0

    return {
        "id": case["id"],
        "query": case["query"],
        "retrieved_documents": retrieved_doc_ids,
        "citations": citations,
        "abstained": abstained,
        "recall_at_5": round(recall_at_5, 4),
        "precision_at_5": round(precision_at_5, 4),
        "faithfulness": round(faithfulness, 4),
        "citation_correctness": round(citation_correctness, 4),
        "completeness": round(completeness, 4),
        "correct_abstention": round(correct_abstention, 4),
        "freshness_correctness": round(freshness_correctness, 4),
        "exception": exception,
        "latency_ms": latency_ms,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [result for result in results if result["exception"] is None]

    def avg(key: str) -> float:
        return round(sum(result[key] for result in evaluated) / len(evaluated), 4) if evaluated else 0

    return {
        "total_cases": len(results),
        "evaluated_cases": len(evaluated),
        "exceptions": sum(1 for result in results if result["exception"]),
        "recall_at_5": avg("recall_at_5"),
        "precision_at_5": avg("precision_at_5"),
        "faithfulness": avg("faithfulness"),
        "citation_correctness": avg("citation_correctness"),
        "completeness": avg("completeness"),
        "correct_abstention": avg("correct_abstention"),
        "freshness_correctness": avg("freshness_correctness"),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in evaluated) / len(evaluated), 2)
        if evaluated else 0,
    }


def _term_coverage(text: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lowered = text.lower()
    hits = sum(1 for term in terms if term.lower() in lowered)
    return hits / len(terms)


def _is_fresh(chunk: dict[str, Any]) -> bool:
    metadata = chunk.get("document_metadata") or {}
    return (
        metadata.get("status") == "active"
        and metadata.get("superseded_by") is None
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG retrieval evaluation.")
    parser.add_argument("--dataset", default=str(DATASET_PATH))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    cases = load_cases(Path(args.dataset))
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']} - {case['query']}")
        results.append(evaluate_case(case))

    report = {
        "name": "rag_report_v1",
        "created_at": datetime.now().isoformat(),
        "dataset": str(args.dataset),
        "summary": summarize(results),
        "results": results,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "rag_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("")
    print("RAG evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
