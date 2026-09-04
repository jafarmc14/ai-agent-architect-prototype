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

LATENCY_BUDGETS_MS = {
    "intent": 3000,
    "extraction": 5000,
    "product_search": 5000,
    "simple_rag": 6000,
    "complex_rag": 9000,
    "agentic_workflow": 12000,
}

COST_BUDGETS_USD = {
    "intent": 0.005,
    "extraction": 0.01,
    "product_search": 0.01,
    "simple_rag": 0.015,
    "complex_rag": 0.03,
    "agentic_workflow": 0.05,
}

COST_PER_CORRECT_ANSWER_BUDGET_USD = 0.05


def parse_latency_map(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    result = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        task, _, value = chunk.partition("=")
        result[task.strip()] = int(value.strip())
    return result


def evaluate(
    quality_score: float = 1.0,
    total_cost_usd: float = 0.0,
    correct_answers: int | None = None,
    measured_latency_ms: dict[str, int] | None = None,
) -> dict:
    measured_latency_ms = measured_latency_ms or {}
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
        item = accounting.to_dict()
        item["latency_budget_ms"] = LATENCY_BUDGETS_MS[case["task"]]
        item["cost_budget_usd"] = COST_BUDGETS_USD[case["task"]]
        if case["task"] in measured_latency_ms:
            item["measured_latency_ms"] = measured_latency_ms[case["task"]]
        results.append(item)

    total_input = sum(item["total_input_tokens"] for item in results)
    correct_answers = len(results) if correct_answers is None else correct_answers
    budget_pass_rate = round(sum(item["within_budget"] for item in results) / len(results), 4)
    per_correct_answer = cost_per_correct_answer(total_cost_usd, correct_answers)
    cost_budget_pass = per_correct_answer is None or per_correct_answer <= COST_PER_CORRECT_ANSWER_BUDGET_USD
    latency_measured = len(measured_latency_ms) > 0
    latency_pass_rates = []
    for item in results:
        if "measured_latency_ms" in item:
            latency_pass_rates.append(item["measured_latency_ms"] <= item["latency_budget_ms"])
    latency_budget_pass_rate = round(sum(latency_pass_rates) / len(latency_pass_rates), 4) if latency_pass_rates else 1.0
    efficiency_target_pass = {
        "tokens": budget_pass_rate == 1.0,
        "latency": (not latency_measured) or latency_budget_pass_rate == 1.0,
        "cost": cost_budget_pass,
    }
    return {
        "name": "efficiency_context_evaluation_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "cases": len(results),
            "budget_passed": sum(item["within_budget"] for item in results),
            "budget_pass_rate": budget_pass_rate,
            "total_input_tokens": total_input,
            "avg_input_tokens": round(total_input / len(results), 2),
            "max_context_utilization_ratio": max(item["context_utilization_ratio"] for item in results),
            "tool_schema_tokens": sum(item["tool_schema_tokens"] for item in results),
            "quality_score": quality_score,
            "total_cost_usd": total_cost_usd,
            "correct_answers": correct_answers,
            "cost_per_correct_answer": per_correct_answer,
            "cost_budget_pass": cost_budget_pass,
            "latency_measured": latency_measured,
            "latency_budget_pass_rate": latency_budget_pass_rate,
            "efficiency_target_pass": efficiency_target_pass,
            "all_efficiency_targets_pass": all(efficiency_target_pass.values()),
        },
        "efficiency_budgets": {
            "latency_ms": LATENCY_BUDGETS_MS,
            "cost_usd": COST_BUDGETS_USD,
            "cost_per_correct_answer_usd": COST_PER_CORRECT_ANSWER_BUDGET_USD,
        },
        "tasks": {item["task"]: item for item in results},
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure per-workflow efficiency budgets for tokens, latency, and cost.")
    parser.add_argument("--output", default="evaluation/reports/token_report_latest.json")
    parser.add_argument("--quality-score", type=float, default=1.0)
    parser.add_argument("--total-cost-usd", type=float, default=0.0)
    parser.add_argument("--correct-answers", type=int)
    parser.add_argument("--latency-ms", default=None, help="Comma-separated measured latency, e.g. intent=1200,simple_rag=4500")
    args = parser.parse_args()
    report = evaluate(
        args.quality_score,
        args.total_cost_usd,
        args.correct_answers,
        parse_latency_map(args.latency_ms),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["all_efficiency_targets_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())