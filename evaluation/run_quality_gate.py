import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = PROJECT_ROOT / "evaluation" / "baselines" / "production_quality_baseline.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"


def nested_value(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise KeyError(path)
        value = value[key]
    return value


def evaluate_metric(metric: dict[str, Any], candidate: float) -> dict[str, Any]:
    baseline = float(metric["baseline"])
    tolerance = float(metric.get("max_regression", 0))
    direction = metric.get("direction", "higher")

    if direction == "higher":
        absolute_limit = float(metric.get("minimum", float("-inf")))
        regression_limit = baseline - tolerance
        effective_limit = max(absolute_limit, regression_limit)
        passed = candidate + 1e-12 >= effective_limit
        regression = baseline - candidate
        comparison = ">="
    elif direction == "lower":
        absolute_limit = float(metric.get("maximum", float("inf")))
        regression_limit = baseline + tolerance
        effective_limit = min(absolute_limit, regression_limit)
        passed = candidate <= effective_limit + 1e-12
        regression = candidate - baseline
        comparison = "<="
    else:
        raise ValueError(f"Unsupported metric direction: {direction!r}")

    return {
        "name": metric["name"],
        "report": metric["report"],
        "path": metric["path"],
        "direction": direction,
        "baseline": baseline,
        "candidate": candidate,
        "max_regression": tolerance,
        "regression": round(regression, 6),
        "effective_limit": effective_limit,
        "comparison": comparison,
        "pass": passed,
    }


def run_gate(baseline_path: Path, report_dir: Path) -> dict[str, Any]:
    config = json.loads(baseline_path.read_text(encoding="utf-8"))
    report_cache: dict[str, dict[str, Any]] = {}
    results = []
    errors = []

    for metric in config.get("metrics", []):
        report_name = metric["report"]
        report_path = report_dir / report_name
        try:
            if report_name not in report_cache:
                report_cache[report_name] = json.loads(report_path.read_text(encoding="utf-8"))
            candidate = float(nested_value(report_cache[report_name], metric["path"]))
            results.append(evaluate_metric(metric, candidate))
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({
                "name": metric.get("name", "unknown"),
                "report": report_name,
                "error": str(exc),
            })

    passed = not errors and bool(results) and all(result["pass"] for result in results)
    return {
        "name": "quality_regression_gate_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline": str(baseline_path),
        "report_dir": str(report_dir),
        "summary": {
            "metrics_total": len(config.get("metrics", [])),
            "metrics_evaluated": len(results),
            "metrics_passed": sum(1 for result in results if result["pass"]),
            "errors": len(errors),
            "quality_regression_blocked": not passed,
            "pass": passed,
        },
        "results": results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail CI when deterministic quality regresses beyond pinned tolerances.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = run_gate(Path(args.baseline), Path(args.report_dir))
    output_path = Path(args.output) if args.output else Path(args.report_dir) / "quality_gate_report_latest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Quality regression gate complete.")
    for result in report["results"]:
        status = "PASS" if result["pass"] else "FAIL"
        print(
            f"[{status}] {result['name']}: candidate={result['candidate']} "
            f"{result['comparison']} limit={result['effective_limit']} "
            f"(baseline={result['baseline']}, tolerance={result['max_regression']})"
        )
    for error in report["errors"]:
        print(f"[ERROR] {error['name']}: {error['error']}")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {output_path}")
    return 0 if report["summary"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
