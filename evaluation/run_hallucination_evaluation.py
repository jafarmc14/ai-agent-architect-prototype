import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "datasets" / "hallucination.jsonl"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.hallucination import audit_response_claims  # noqa: E402
from core.privacy import redact_for_logs  # noqa: E402


TARGETS = {
    "unsupported_claim_rate": 0.01,
    "unsupported_critical_claims": 0,
}


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if line:
                case = json.loads(line)
                case["line_number"] = line_number
                cases.append(case)
    return cases


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    audit = audit_response_claims(
        case["response"],
        tool_outputs=case.get("tool_outputs", []),
        rag_evidence=case.get("rag_evidence", ""),
    )
    expected_unsupported_critical = int(case.get("expected_unsupported_critical", 0))
    expected_match = audit.unsupported_critical_claim_count == expected_unsupported_critical
    critical_target_pass = audit.unsupported_critical_claim_count == 0
    return {
        "id": case["id"],
        "response": redact_for_logs(case["response"]),
        "expected_unsupported_critical": expected_unsupported_critical,
        "unsupported_claim_count": len(audit.unsupported_claims),
        "unsupported_critical_claim_count": audit.unsupported_critical_claim_count,
        "unsupported_claim_rate": audit.unsupported_claim_rate,
        "should_abstain": audit.should_abstain,
        "expected_match": expected_match,
        "critical_target_pass": critical_target_pass,
        "claims": [
            {
                "text": redact_for_logs(claim.text),
                "source": claim.source.value,
                "critical": claim.critical,
                "supported": claim.supported,
                "reason": claim.reason,
                "evidence_type": claim.evidence_type,
            }
            for claim in audit.claims
        ],
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    target_results = [result for result in results if result["expected_unsupported_critical"] == 0]
    total_claims = sum(len(result["claims"]) for result in target_results)
    unsupported_claims = sum(result["unsupported_claim_count"] for result in target_results)
    unsupported_critical = sum(result["unsupported_critical_claim_count"] for result in target_results)
    unsupported_rate = round(unsupported_claims / total_claims, 4) if total_claims else 0
    return {
        "total_cases": len(results),
        "target_cases": len(target_results),
        "target_claims": total_claims,
        "expected_detector_matches": sum(1 for result in results if result["expected_match"]),
        "expected_detector_match_rate": round(
            sum(1 for result in results if result["expected_match"]) / len(results),
            4,
        ) if results else 0,
        "unsupported_claims": unsupported_claims,
        "unsupported_claim_rate": unsupported_rate,
        "unsupported_critical_claims": unsupported_critical,
        "abstentions": sum(1 for result in results if result["should_abstain"]),
        "targets": TARGETS,
        "target_pass": {
            "unsupported_claim_rate": unsupported_rate < TARGETS["unsupported_claim_rate"],
            "unsupported_critical_claims": unsupported_critical == TARGETS["unsupported_critical_claims"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hallucination control evaluation.")
    parser.add_argument("--dataset", default=str(DATASET_PATH))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()

    cases = load_cases(Path(args.dataset))
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']}")
        results.append(evaluate_case(case))

    report = {
        "name": "hallucination_report_v1",
        "created_at": datetime.now().isoformat(),
        "dataset": str(args.dataset),
        "summary": summarize(results),
        "results": results,
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "hallucination_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("")
    print("Hallucination evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")
    return 0 if all(report["summary"]["target_pass"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
