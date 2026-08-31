import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
BASELINE_DIR = PROJECT_ROOT / "evaluation" / "datasets" / "baseline"
PRODUCT_SEARCH_DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "product_search.jsonl"
INTENT_DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "intent.jsonl"
TARGET_SCHEMA_VALIDITY = 0.999

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthenticatedUser, RequestContext, authorize_tool  # noqa: E402
from core.structured_outputs import (  # noqa: E402
    FilterOutput,
    IntentOutput,
    PolicyDecisionOutput,
    RoutingOutput,
    ToolArgumentsOutput,
    build_filter_output,
    build_intent_output,
    build_policy_decision_output,
    build_routing_output,
    build_tool_arguments_output,
    validate_structured_output,
)


SCHEMA_BY_NAME = {
    "intent": IntentOutput,
    "filters": FilterOutput,
    "routing": RoutingOutput,
    "tool_arguments": ToolArgumentsOutput,
    "policy_decision": PolicyDecisionOutput,
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_baseline_cases() -> list[dict[str, Any]]:
    cases = []
    for path in sorted(BASELINE_DIR.glob("*.jsonl")):
        cases.extend(load_jsonl(path))
    return cases


def build_cases() -> list[dict[str, Any]]:
    cases = []
    context = _context()

    for case in load_baseline_cases():
        query = case["query"]
        cases.append(_case("intent", case["id"], build_intent_output(query)))
        cases.append(_case("routing", case["id"], build_routing_output(query, context)))

    for case in load_jsonl(INTENT_DATASET):
        query = case["query"]
        cases.append(_case("intent", case["id"], build_intent_output(query)))
        cases.append(_case("routing", case["id"], build_routing_output(query, context)))

    for case in load_jsonl(PRODUCT_SEARCH_DATASET):
        query_input = case.get("input", {})
        cases.append(_case("filters", case["id"], build_filter_output(**query_input)))

    tool_cases = [
        ("check_stock", {"product_name": "Nike"}),
        ("check_order_status", {"order_id": "ORD001"}),
        ("search_products", {"query": "shoes under Rp 500,000", "max_price": 500000}),
        ("cancel_customer_order", {"order_id": "ORD002"}),
        ("update_shipping_address", {"order_id": "ORD005", "new_address": "Jl. Sudirman No. 100, Jakarta"}),
        ("add_product_to_cart", {"product_name": "Nike shoes", "quantity": 2}),
        ("view_shopping_cart", {}),
        ("clear_shopping_cart", {}),
        ("search_knowledge_base", {"query": "return policy"}),
        ("escalate_to_human", {"customer_message": "I need a human agent", "priority": "High"}),
    ]
    exposed_tools = {tool_name for tool_name, _ in tool_cases}
    for tool_name, args in tool_cases:
        cases.append(_case(
            "tool_arguments",
            tool_name,
            build_tool_arguments_output(tool_name, args, exposed_tools, context),
        ))

    for tool_name, _ in tool_cases:
        authorization = authorize_tool(tool_name, context)
        cases.append(_case(
            "policy_decision",
            tool_name,
            build_policy_decision_output(authorization, context, required_role="customer"),
        ))

    cases.extend(_invalid_output_retry_cases())
    return cases


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    schema_model = SCHEMA_BY_NAME[case["schema"]]
    result = validate_structured_output(case["payload"], schema_model, max_retries=case.get("max_retries", 1))
    return {
        "id": case["id"],
        "schema": case["schema"],
        "valid": result.valid,
        "attempts": result.attempts,
        "repaired": result.repaired,
        "errors": result.errors,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    valid = sum(1 for result in results if result["valid"])
    schema_validity = round(valid / total, 6) if total else 0
    by_schema = {}
    for schema in sorted(SCHEMA_BY_NAME):
        schema_results = [result for result in results if result["schema"] == schema]
        schema_total = len(schema_results)
        schema_valid = sum(1 for result in schema_results if result["valid"])
        by_schema[schema] = {
            "total": schema_total,
            "valid": schema_valid,
            "validity_rate": round(schema_valid / schema_total, 6) if schema_total else 0,
        }
    return {
        "total_cases": total,
        "valid": valid,
        "invalid": total - valid,
        "repaired": sum(1 for result in results if result["repaired"]),
        "schema_validity_rate": schema_validity,
        "target_schema_validity": TARGET_SCHEMA_VALIDITY,
        "target_pass": schema_validity >= TARGET_SCHEMA_VALIDITY,
        "by_schema": by_schema,
    }


def _case(schema: str, source_id: str, payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    return {
        "id": f"{schema}_{source_id}",
        "schema": schema,
        "payload": payload,
    }


def _invalid_output_retry_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "intent_retry_wrapped_json",
            "schema": "intent",
            "payload": 'Model output:\n{"intent":"UNKNOWN","confidence":0.5,"language":"English","requires_tools":false,"security_flags":[]}',
            "max_retries": 1,
        },
        {
            "id": "routing_retry_wrapped_json",
            "schema": "routing",
            "payload": '```json\n{"intent":"UNKNOWN","workflow":"agent_loop","use_agent_loop":true,"reason":"fallback","exposed_tools":[],"security_flags":[]}\n```',
            "max_retries": 1,
        },
    ]


def _context() -> RequestContext:
    return RequestContext(
        session_id="structured-eval",
        user=AuthenticatedUser(
            user_id="11111111-1111-1111-1111-111111111111",
            email="structured.evaluator@example.local",
            name="Structured Evaluator",
            role="manager",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run structured output schema evaluation.")
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    results = [evaluate_case(case) for case in build_cases()]
    report = {
        "name": "structured_output_report_v1",
        "created_at": datetime.now().isoformat(),
        "summary": summarize(results),
        "results": results,
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "structured_output_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Structured output evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")
    return 0 if report["summary"]["target_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
