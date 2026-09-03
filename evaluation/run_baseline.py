import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "evaluation" / "datasets" / "baseline"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.privacy import redact_for_logs  # noqa: E402
from core.optimization import summarize_token_trace  # noqa: E402


TOOL_TARGETS = {
    "tool_selection_rate": 0.98,
    "argument_accuracy_rate": 0.99,
}


def load_cases(dataset_dir: Path) -> list[dict]:
    cases = []
    for path in sorted(dataset_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                case = json.loads(line)
                case["dataset_file"] = path.name
                case["line_number"] = line_number
                cases.append(case)
    return cases


def filter_cases(cases: list[dict], selected_files: list[str]) -> list[dict]:
    if not selected_files:
        return cases

    normalized_files = {
        name if name.endswith(".jsonl") else f"{name}.jsonl"
        for name in selected_files
    }
    return [case for case in cases if case["dataset_file"] in normalized_files]


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize(value):
    if isinstance(value, str):
        return " ".join(value.lower().strip().split())
    return value


PRODUCT_ARGUMENT_ALIASES = {
    "nike shoes": "nike",
    "nike shoe": "nike",
    "sepatu nike": "nike",
    "kaos hitam": "black plain t-shirt",
    "kaos polos hitam": "black plain t-shirt",
    "baju hitam": "black plain t-shirt",
    "t-shirt hitam": "black plain t-shirt",
    "tas eiger": "eiger",
    "headphone sony": "sony",
    "sony headphone": "sony",
    "sony headphones": "sony",
    "jam casio": "casio",
}


def normalize_argument(key, value):
    normalized = normalize(value)
    if key == "product_name" and isinstance(normalized, str):
        return PRODUCT_ARGUMENT_ALIASES.get(normalized, normalized)
    return normalized


def values_match(expected, actual) -> bool:
    expected_norm = normalize(expected)
    actual_norm = normalize(actual)

    if expected_norm == actual_norm:
        return True

    if isinstance(expected_norm, str) and isinstance(actual_norm, str):
        return expected_norm in actual_norm or actual_norm in expected_norm

    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(expected) == float(actual)

    return False


def expected_args_match(expected_args, actual_args) -> tuple[bool, list[str]]:
    mismatches = []
    for key, expected_value in expected_args.items():
        if key not in actual_args:
            mismatches.append(f"missing argument '{key}'")
            continue
        expected_norm = normalize_argument(key, expected_value)
        actual_norm = normalize_argument(key, actual_args[key])
        if not values_match(expected_norm, actual_norm):
            mismatches.append(
                f"argument '{key}' expected {expected_value!r}, got {actual_args[key]!r}"
            )
    return len(mismatches) == 0, mismatches


def evaluate_case(case: dict, agent_module, database_module) -> dict:
    expected_tools = as_list(case.get("expected_tool"))
    expected_arguments = as_list(case.get("expected_arguments"))
    expected_pairs = list(zip(expected_tools, expected_arguments))

    agent_module.reset_chat_history()

    start = time.perf_counter()
    result = agent_module.get_agent_response_with_trace(
        case["query"],
        auth_token=evaluation_auth_token(),
        session_id="baseline-evaluation",
    )
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    actual_calls = result["tool_calls"]
    actual_tools = [call["name"] for call in actual_calls]

    tool_selection_pass = actual_tools == expected_tools

    argument_mismatches = []
    if len(actual_calls) != len(expected_pairs):
        argument_mismatches.append(
            f"expected {len(expected_pairs)} tool call(s), got {len(actual_calls)}"
        )

    for index, (expected_tool, expected_args) in enumerate(expected_pairs):
        if index >= len(actual_calls):
            continue
        actual_call = actual_calls[index]
        if actual_call["name"] != expected_tool:
            argument_mismatches.append(
                f"tool #{index + 1} expected {expected_tool!r}, got {actual_call['name']!r}"
            )
            continue
        args_pass, mismatches = expected_args_match(expected_args, actual_call["args"])
        argument_mismatches.extend(mismatches)

    argument_accuracy_pass = len(argument_mismatches) == 0
    response_returned = bool(result["response"].strip())
    exception = result["exception"]
    token_usage = summarize_token_trace(result)
    claim_audit = redact_for_logs(result.get("claim_audit") or {})

    return {
        "id": case["id"],
        "dataset_file": case["dataset_file"],
        "query": redact_for_logs(case["query"]),
        "expected_tool": case.get("expected_tool"),
        "expected_arguments": redact_for_logs(case.get("expected_arguments")),
        "actual_tools": actual_tools,
        "actual_tool_calls": [
            {
                "name": call["name"],
                "args": redact_for_logs(call["args"]),
                "output_preview": redact_for_logs(call["output"])[:500],
            }
            for call in actual_calls
        ],
        "tool_selection_pass": tool_selection_pass,
        "argument_accuracy_pass": argument_accuracy_pass,
        "argument_mismatches": argument_mismatches,
        "response_returned": response_returned,
        "response_preview": redact_for_logs(result["response"])[:1000],
        "prompt": redact_for_logs(result.get("prompt")),
        "exception": redact_for_logs(exception),
        "latency_ms": latency_ms,
        "token_usage": token_usage,
        "claim_audit": claim_audit,
        "hallucination_abstained": bool(result.get("hallucination_abstained")),
        "citation_present": bool(re.search(r"\[C\d+\]", result["response"])),
        "access": case.get("access"),
        "risk": case.get("risk"),
        "skipped": False,
        "skip_reason": None,
    }


def evaluation_auth_token() -> str:
    from core.auth import create_session_token

    return create_session_token(
        user_id="00000000-0000-0000-0000-000000000001",
        email="baseline.evaluator@example.local",
        name="Baseline Evaluator",
        role="manager",
        tenant_id="default",
    )


def skipped_case(case: dict, reason: str) -> dict:
    return {
        "id": case["id"],
        "dataset_file": case["dataset_file"],
        "query": redact_for_logs(case["query"]),
        "expected_tool": case.get("expected_tool"),
        "expected_arguments": redact_for_logs(case.get("expected_arguments")),
        "actual_tools": [],
        "actual_tool_calls": [],
        "tool_selection_pass": False,
        "argument_accuracy_pass": False,
        "argument_mismatches": [],
        "response_returned": False,
        "response_preview": "",
        "exception": None,
        "latency_ms": 0,
        "token_usage": {},
        "claim_audit": {},
        "hallucination_abstained": False,
        "citation_present": False,
        "access": case.get("access"),
        "risk": case.get("risk"),
        "skipped": True,
        "skip_reason": reason,
    }


def restore_database(db_path: Path, backup_path: Path) -> None:
    if backup_path.exists():
        shutil.copy2(backup_path, db_path)


def is_rate_limit_exception(exception: str | None) -> bool:
    if not exception:
        return False
    exception_lower = exception.lower()
    return "rate limit" in exception_lower or "code': 429" in exception_lower or "error code: 429" in exception_lower


def summarize(results: list[dict]) -> dict:
    total = len(results)
    evaluated = [result for result in results if not result.get("skipped")]
    skipped = [result for result in results if result.get("skipped")]
    latencies = [result["latency_ms"] for result in evaluated]

    def count(key):
        return sum(1 for result in evaluated if result[key])

    evaluated_total = len(evaluated)

    return {
        "total_cases": total,
        "evaluated_cases": evaluated_total,
        "skipped_cases": len(skipped),
        "tool_selection_passed": count("tool_selection_pass"),
        "tool_selection_rate": round(count("tool_selection_pass") / evaluated_total, 4) if evaluated_total else 0,
        "argument_accuracy_passed": count("argument_accuracy_pass"),
        "argument_accuracy_rate": round(count("argument_accuracy_pass") / evaluated_total, 4) if evaluated_total else 0,
        "responses_returned": count("response_returned"),
        "response_return_rate": round(count("response_returned") / evaluated_total, 4) if evaluated_total else 0,
        "exceptions": sum(1 for result in evaluated if result["exception"]),
        "rate_limit_exceptions": sum(1 for result in evaluated if is_rate_limit_exception(result["exception"])),
        "avg_latency_ms": round(sum(latencies) / evaluated_total, 2) if evaluated_total else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "min_latency_ms": min(latencies) if latencies else 0,
        "tool_targets": TOOL_TARGETS,
        "tool_target_pass": {
            "tool_selection_rate": (
                (count("tool_selection_pass") / evaluated_total) >= TOOL_TARGETS["tool_selection_rate"]
            ) if evaluated_total else False,
            "argument_accuracy_rate": (
                (count("argument_accuracy_pass") / evaluated_total) >= TOOL_TARGETS["argument_accuracy_rate"]
            ) if evaluated_total else False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run baseline evaluation cases.")
    parser.add_argument("--dataset-dir", default=str(DATASET_DIR))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--delay-seconds", type=float, default=0)
    parser.add_argument("--continue-on-rate-limit", action="store_true")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    report_dir = Path(args.report_dir)
    cases = filter_cases(load_cases(dataset_dir), args.files)
    if args.offset > 0:
        cases = cases[args.offset :]
    if args.limit > 0:
        cases = cases[: args.limit]

    import agent
    import database
    from configs import get_settings

    report_dir.mkdir(parents=True, exist_ok=True)

    database_provider = get_settings().database_provider
    db_path = Path(database.DB_PATH)
    if database_provider == "sqlite" and not db_path.exists():
        database.init_database()

    results = []
    with TemporaryDirectory() as tmp_dir:
        if database_provider == "sqlite":
            original_backup_path = Path(tmp_dir) / "toko_original.db"
            baseline_backup_path = Path(tmp_dir) / "toko_baseline.db"

            shutil.copy2(db_path, original_backup_path)
            database.reset_database()
            shutil.copy2(db_path, baseline_backup_path)
        else:
            original_backup_path = None
            baseline_backup_path = None

        for index, case in enumerate(cases, start=1):
            if database_provider == "sqlite":
                restore_database(db_path, baseline_backup_path)
            print(f"[{index}/{len(cases)}] {case['id']} - {case['query']}")
            result = evaluate_case(case, agent, database)
            results.append(result)

            if is_rate_limit_exception(result["exception"]) and not args.continue_on_rate_limit:
                remaining = cases[index:]
                for skipped in remaining:
                    results.append(skipped_case(skipped, "Skipped because OpenRouter rate limit was reached."))
                print("Rate limit detected. Stopping early; remaining cases marked as skipped.")
                break

            if args.delay_seconds > 0 and index < len(cases):
                time.sleep(args.delay_seconds)

        if database_provider == "sqlite":
            restore_database(db_path, original_backup_path)

    report = {
        "name": "baseline_report_v1",
        "created_at": datetime.now().isoformat(),
        "environment": getattr(agent, "get_llm_config", lambda: {})().get("environment"),
        "database_provider": database_provider,
        "provider": getattr(agent, "LLM_PROVIDER", None),
        "model": getattr(agent, "LLM_MODEL", getattr(agent, "OPENROUTER_MODEL", None)),
        "model_version": getattr(agent, "get_llm_config", lambda: {})().get("model_version"),
        "model_governance": getattr(agent, "get_llm_config", lambda: {})().get("model_governance"),
        "dataset_dir": str(dataset_dir),
        "summary": summarize(results),
        "results": results,
    }

    latest_path = report_dir / "baseline_report_latest.json"

    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("")
    print("Baseline evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
