import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def compare(baseline: dict, candidate: dict, threshold: float = 0.20) -> dict:
    failures = []
    warnings = []
    baseline_quality = float(baseline.get("summary", {}).get("quality_score", 0))
    candidate_quality = float(candidate.get("summary", {}).get("quality_score", 0))
    for task, current in candidate.get("tasks", {}).items():
        previous = baseline.get("tasks", {}).get(task)
        if not previous:
            warnings.append(f"No baseline exists for task '{task}'.")
            continue
        old_tokens = int(previous.get("total_input_tokens", 0))
        new_tokens = int(current.get("total_input_tokens", 0))
        increase = (new_tokens - old_tokens) / max(old_tokens, 1)
        if increase > threshold:
            message = f"{task}: tokens increased {increase:.1%} ({old_tokens} -> {new_tokens})"
            if candidate_quality <= baseline_quality:
                failures.append(message + " without quality gain")
            else:
                warnings.append(message + " with measured quality gain")
        if not current.get("within_budget", False):
            failures.append(f"{task}: input budget exceeded")
    return {
        "status": "FAIL" if failures else "PASS",
        "threshold": threshold,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail token regressions above the allowed threshold.")
    parser.add_argument("--baseline", default="evaluation/baselines/token_baseline.json")
    parser.add_argument("--candidate", default="evaluation/reports/token_report_latest.json")
    parser.add_argument("--output", default="evaluation/reports/token_regression_report_latest.json")
    parser.add_argument("--threshold", type=float, default=0.20)
    args = parser.parse_args()
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    report = compare(baseline, candidate, args.threshold)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
