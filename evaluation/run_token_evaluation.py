import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.optimization import account_llm_context, cost_per_correct_answer  # noqa: E402
from core.prompts import get_task_prompt  # noqa: E402
from core.tools import tools_by_name  # noqa: E402


CASES = [
    {"task": "intent", "query": "What is the return policy?", "tools": [], "conversation": "", "retrieval": ""},
    {"task": "extraction", "query": "Find black shoes size 42 under Rp500,000", "tools": [], "conversation": "", "retrieval": ""},
    {"task": "product_search", "query": "Find comfortable shoes under Rp1,500,000", "tools": [], "conversation": "User previously asked for shoes.", "retrieval": ""},
    {"task": "simple_rag", "query": "What is the return policy?", "tools": ["search_knowledge_base"], "conversation": "", "retrieval": "[C1] Official return policy evidence. Returns are accepted within 7 days."},
    {"task": "complex_rag", "query": "My damaged item needs a refund and human review", "tools": ["search_knowledge_base", "escalate_to_human"], "conversation": "User reported a damaged order.", "retrieval": "[C1] Official refund evidence.\n[C2] Official warranty evidence."},
    {"task": "agentic_workflow", "query": "Check my order and help if it is damaged", "tools": ["check_order_status", "search_knowledge_base", "escalate_to_human"], "conversation": "User discussed order ORD001 in two recent turns.", "retrieval": "Order tool output and authorized policy evidence."},
]


def evaluate(quality_score: float = 1.0, total_cost_usd: float = 0.0, correct_answers: int | None = None) -> dict:
    results = []
    for case in CASES:
        exposed = [tools_by_name[name] for name in case["tools"]]
        accounting = account_llm_context(
            task=case["task"],
            system_prompt=get_task_prompt(case["task"]),
            user_input=case["query"],
            conversation=case["conversation"],
            retrieval_context=case["retrieval"],
            tools=exposed,
        )
        results.append(accounting.to_dict())

    total_input = sum(item["total_input_tokens"] for item in results)
    correct_answers = len(results) if correct_answers is None else correct_answers
    return {
        "name": "token_context_evaluation_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "cases": len(results),
            "budget_passed": sum(item["within_budget"] for item in results),
            "budget_pass_rate": round(sum(item["within_budget"] for item in results) / len(results), 4),
            "total_input_tokens": total_input,
            "avg_input_tokens": round(total_input / len(results), 2),
            "max_context_utilization_ratio": max(item["context_utilization_ratio"] for item in results),
            "tool_schema_tokens": sum(item["tool_schema_tokens"] for item in results),
            "quality_score": quality_score,
            "total_cost_usd": total_cost_usd,
            "correct_answers": correct_answers,
            "cost_per_correct_answer": cost_per_correct_answer(total_cost_usd, correct_answers),
        },
        "tasks": {item["task"]: item for item in results},
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure Phase 27 token budgets deterministically.")
    parser.add_argument("--output", default="evaluation/reports/token_report_latest.json")
    parser.add_argument("--quality-score", type=float, default=1.0)
    parser.add_argument("--total-cost-usd", type=float, default=0.0)
    parser.add_argument("--correct-answers", type=int)
    args = parser.parse_args()
    report = evaluate(args.quality_score, args.total_cost_usd, args.correct_answers)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["budget_pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
