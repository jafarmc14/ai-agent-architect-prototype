import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.base import LLMResponse  # noqa: E402
from evaluation.test_provider_fallback import HTTPFailure, _gateway  # noqa: E402


TARGET_RECOVERY_RATE = 0.99
FAULT_FACTORIES = {
    "429": lambda: HTTPFailure(429),
    "500": lambda: HTTPFailure(500),
    "timeout": lambda: TimeoutError("timed out"),
    "invalid_response": lambda: LLMResponse(text=""),
    "connection_failure": lambda: ConnectionError("connection refused"),
}


def run_evaluation(cases_per_failure: int = 20) -> dict:
    results = []
    for failure_name, factory in FAULT_FACTORIES.items():
        for index in range(1, cases_per_failure + 1):
            gateway, _, _, repository = _gateway(factory())
            recovered = False
            error = None
            try:
                response = gateway.generate_sync(
                    [{"role": "user", "content": f"fallback evaluation {failure_name} {index}"}],
                    task="orders",
                )
                recovered = response.text == "fallback success"
            except Exception as exc:  # noqa: BLE001
                error = exc.__class__.__name__
            final_request = repository.requests[-1] if repository.requests else {}
            fallback = (final_request.get("metadata") or {}).get("fallback") or {}
            results.append({
                "id": f"{failure_name}_{index:03d}",
                "failure": failure_name,
                "recovered": recovered,
                "final_provider": final_request.get("provider"),
                "attempt_count": fallback.get("attempt_count"),
                "error": error,
            })

    total = len(results)
    recovered = sum(item["recovered"] for item in results)
    by_failure = {}
    for failure_name in FAULT_FACTORIES:
        matching = [item for item in results if item["failure"] == failure_name]
        passed = sum(item["recovered"] for item in matching)
        by_failure[failure_name] = {
            "cases": len(matching),
            "recovered": passed,
            "recovery_rate": round(passed / len(matching), 4) if matching else 0.0,
        }
    recovery_rate = round(recovered / total, 4) if total else 0.0
    return {
        "name": "provider_fallback_evaluation_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_cases": total,
            "recovered": recovered,
            "recovery_rate": recovery_rate,
            "target_recovery_rate": TARGET_RECOVERY_RATE,
            "target_pass": recovery_rate >= TARGET_RECOVERY_RATE,
            "external_provider_calls": 0,
        },
        "by_failure": by_failure,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic provider fallback fault injection.")
    parser.add_argument("--cases-per-failure", type=int, default=20)
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = parser.parse_args()
    if args.cases_per_failure < 1:
        parser.error("--cases-per-failure must be at least 1")

    report = run_evaluation(args.cases_per_failure)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    output = report_dir / "provider_fallback_report_latest.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Provider fallback evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {output}")
    return 0 if report["summary"]["target_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
