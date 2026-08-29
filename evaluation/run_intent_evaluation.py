import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "datasets" / "intent.jsonl"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
TARGET_MACRO_F1 = 0.95

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.workflows import Intent, classify_intent, route_intent  # noqa: E402


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


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    predicted_intent = classify_intent(case["query"]).value
    route = route_intent(case["query"])
    expected_intent = case["expected_intent"]
    return {
        "id": case["id"],
        "query": case["query"],
        "expected_intent": expected_intent,
        "predicted_intent": predicted_intent,
        "pass": predicted_intent == expected_intent,
        "workflow": route.workflow,
        "use_agent_loop": route.use_agent_loop,
        "route_reason": route.reason,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [intent.value for intent in Intent]
    by_label = {}
    for label in labels:
        tp = sum(1 for result in results if result["expected_intent"] == label and result["predicted_intent"] == label)
        fp = sum(1 for result in results if result["expected_intent"] != label and result["predicted_intent"] == label)
        fn = sum(1 for result in results if result["expected_intent"] == label and result["predicted_intent"] != label)
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        by_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(1 for result in results if result["expected_intent"] == label),
        }

    macro_f1 = sum(metrics["f1"] for metrics in by_label.values()) / len(by_label)
    return {
        "total_cases": len(results),
        "passed": sum(1 for result in results if result["pass"]),
        "accuracy": round(sum(1 for result in results if result["pass"]) / len(results), 4) if results else 0,
        "macro_f1": round(macro_f1, 4),
        "target_macro_f1": TARGET_MACRO_F1,
        "target_pass": macro_f1 >= TARGET_MACRO_F1,
        "by_intent": by_label,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run explicit intent router evaluation.")
    parser.add_argument("--dataset", default=str(DATASET_PATH))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    cases = load_cases(Path(args.dataset))
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']} - {case['query']}")
        results.append(evaluate_case(case))

    report = {
        "name": "intent_router_report_v1",
        "created_at": datetime.now().isoformat(),
        "dataset": str(args.dataset),
        "summary": summarize(results),
        "results": results,
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "intent_router_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("")
    print("Intent router evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")
    return 0 if report["summary"]["target_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
