import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
REGRESSION_DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "regression" / "bugs.jsonl"


CHANGE_AREA_COMMANDS = {
    "prompt": [
        ["evaluation/test_prompt_versioning.py"],
        ["evaluation/test_prompt_injection_defense.py"],
        ["evaluation/test_scope_control.py"],
        ["evaluation/test_structured_outputs.py"],
        ["evaluation/test_conversation_state.py"],
        ["evaluation/test_token_optimization.py"],
    ],
    "model": [
        ["evaluation/test_circuit_breaker.py"],
        ["evaluation/test_provider_fallback.py"],
        ["evaluation/test_model_routing.py"],
        ["evaluation/test_provider_benchmark.py"],
        ["evaluation/test_provider_integration.py"],
        ["evaluation/test_model_governance.py"],
        ["evaluation/test_prompt_versioning.py"],
        ["evaluation/test_structured_outputs.py"],
        ["evaluation/test_full_evaluation_framework.py"],
        ["evaluation/test_regression_framework.py"],
    ],
    "embedding": [
        ["evaluation/test_product_search_extraction.py"],
        ["evaluation/test_rag_retrieval.py"],
    ],
    "retrieval": [
        ["evaluation/test_product_search_extraction.py"],
        ["evaluation/test_rag_retrieval.py"],
        ["evaluation/run_product_search_evaluation.py"],
        ["evaluation/run_rag_evaluation.py"],
    ],
    "reranker": [
        ["evaluation/test_product_search_extraction.py"],
        ["evaluation/run_product_search_evaluation.py"],
    ],
    "chunking": [
        ["evaluation/test_document_ingestion.py"],
        ["evaluation/test_rag_retrieval.py"],
        ["evaluation/run_rag_evaluation.py"],
    ],
    "tools": [
        ["evaluation/test_agent_loop_safety.py"],
        ["evaluation/test_resource_protection.py"],
        ["evaluation/test_controlled_write_actions.py"],
        ["evaluation/test_human_escalation.py"],
        ["evaluation/test_hallucination_control.py"],
        ["evaluation/test_observability.py"],
    ],
    "business_rules": [
        ["evaluation/test_agent_loop_safety.py"],
        ["evaluation/test_resource_protection.py"],
        ["evaluation/test_controlled_write_actions.py"],
        ["evaluation/test_human_escalation.py"],
        ["evaluation/test_hallucination_control.py"],
        ["evaluation/test_quality_gate.py"],
        ["evaluation/test_ci_pipeline.py"],
    ],
    "authorization": [
        ["evaluation/test_auth_context.py"],
        ["evaluation/test_rbac_authorization.py"],
        ["evaluation/run_authorization_evaluation.py"],
    ],
}

DEFAULT_AREAS = [
    "prompt",
    "model",
    "embedding",
    "retrieval",
    "reranker",
    "chunking",
    "tools",
    "business_rules",
    "authorization",
]


def load_bug_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["line_number"] = line_number
            rows.append(row)
    return rows


def validate_bug_cases(cases: list[dict[str, Any]], selected_areas: set[str]) -> dict[str, Any]:
    errors = []
    ids = set()
    coverage = {area: 0 for area in DEFAULT_AREAS}
    selected_cases = []
    for case in cases:
        case_id = case.get("id", "")
        if not case_id:
            errors.append(f"line {case.get('line_number')}: missing id")
        if case_id in ids:
            errors.append(f"duplicate id: {case_id}")
        ids.add(case_id)
        if not case.get("query"):
            errors.append(f"{case_id}: missing query")
        if "expected_arguments" not in case:
            errors.append(f"{case_id}: missing expected_arguments")
        case_areas = set(case.get("change_areas") or [])
        unknown_areas = sorted(case_areas - set(DEFAULT_AREAS))
        if unknown_areas:
            errors.append(f"{case_id}: unknown change_areas {unknown_areas}")
        for area in case_areas:
            if area in coverage:
                coverage[area] += 1
        if not selected_areas or case_areas & selected_areas:
            selected_cases.append(case)

    return {
        "total_cases": len(cases),
        "selected_cases": len(selected_cases),
        "coverage": coverage,
        "errors": errors,
        "pass": not errors and len(cases) > 0,
    }


def run_commands(selected_areas: list[str], quick: bool) -> list[dict[str, Any]]:
    commands = []
    seen = set()
    for area in selected_areas:
        for command in CHANGE_AREA_COMMANDS.get(area, []):
            key = tuple(command)
            if key not in seen:
                seen.add(key)
                commands.append(command)
    if quick:
        commands = [command for command in commands if not command[0].startswith("evaluation/run_")]

    results = []
    for command in commands:
        display = " ".join([Path(sys.executable).name, *command])
        print(f"[regression] {display}")
        start = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, *command],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "command": [sys.executable, *command],
                "returncode": completed.returncode,
                "passed": completed.returncode == 0,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )
    return results


def run_llm_bug_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import agent

    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[llm regression {index}/{len(cases)}] {case['id']}")
        start = time.perf_counter()
        trace = agent.get_agent_response_with_trace(case["query"], session_id=f"regression-{case['id']}")
        response = trace.get("response", "")
        actual_tools = [call["name"] for call in trace.get("tool_calls", [])]
        expected_tool = case.get("expected_tool")
        expected_tools = [] if expected_tool is None else expected_tool if isinstance(expected_tool, list) else [expected_tool]
        assertion_result = evaluate_response_assertions(response, case.get("assertions", {}))
        tool_pass = actual_tools == expected_tools
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected_tools": expected_tools,
                "actual_tools": actual_tools,
                "tool_pass": tool_pass,
                "assertions_pass": assertion_result["pass"],
                "assertion_errors": assertion_result["errors"],
                "exception": trace.get("exception"),
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        )
    return results


def evaluate_response_assertions(response: str, assertions: dict[str, Any]) -> dict[str, Any]:
    lowered = response.lower()
    errors = []
    must_contain_any = assertions.get("response_must_contain_any") or []
    if must_contain_any and not any(item.lower() in lowered for item in must_contain_any):
        errors.append(f"none of response_must_contain_any found: {must_contain_any}")
    for item in assertions.get("response_must_not_contain") or []:
        if item.lower() in lowered:
            errors.append(f"forbidden response text found: {item!r}")
    return {"pass": not errors, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run regression checks for selected change areas.")
    parser.add_argument("--areas", nargs="*", default=DEFAULT_AREAS, choices=DEFAULT_AREAS)
    parser.add_argument("--quick", action="store_true", help="Skip heavier runner scripts and run unit-style checks only.")
    parser.add_argument("--include-llm", action="store_true", help="Run bug regression cases through the agent/LLM.")
    parser.add_argument("--dataset", default=str(REGRESSION_DATASET))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    selected_areas = args.areas or DEFAULT_AREAS
    selected_area_set = set(selected_areas)
    bug_cases = load_bug_cases(Path(args.dataset))
    validation = validate_bug_cases(bug_cases, selected_area_set)
    selected_bug_cases = [
        case for case in bug_cases
        if not case.get("change_areas") or set(case.get("change_areas", [])) & selected_area_set
    ]
    command_results = run_commands(selected_areas, quick=args.quick)
    llm_results = run_llm_bug_cases(selected_bug_cases) if args.include_llm else []

    summary = {
        "selected_areas": selected_areas,
        "bug_dataset_valid": validation["pass"],
        "bug_cases_total": validation["total_cases"],
        "bug_cases_selected": validation["selected_cases"],
        "commands_total": len(command_results),
        "commands_passed": sum(1 for result in command_results if result["passed"]),
        "llm_regression_enabled": args.include_llm,
        "llm_cases_total": len(llm_results),
        "llm_cases_passed": sum(
            1 for result in llm_results
            if result["tool_pass"] and result["assertions_pass"] and not result["exception"]
        ),
    }
    summary["pass"] = (
        validation["pass"]
        and summary["commands_passed"] == summary["commands_total"]
        and (
            not args.include_llm
            or summary["llm_cases_passed"] == summary["llm_cases_total"]
        )
    )

    report = {
        "name": "regression_report_v1",
        "created_at": datetime.now().isoformat(),
        "summary": summary,
        "bug_dataset_validation": validation,
        "commands": command_results,
        "llm_bug_results": llm_results,
        "policy": {
            "every_bug_becomes_regression_case": True,
            "run_on_change_areas": DEFAULT_AREAS,
            "default_mode": "deterministic/no external LLM calls",
        },
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "regression_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Regression run complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Report saved to: {latest_path}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
