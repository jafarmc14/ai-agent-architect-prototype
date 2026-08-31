import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
BASELINE_DIR = PROJECT_ROOT / "evaluation" / "datasets" / "baseline"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.framework import calibration_from_reports, deterministic_metrics_from_reports  # noqa: E402
from evaluation.framework.deterministic import load_latest_reports  # noqa: E402
from evaluation.framework.subjective_judge import SUBJECTIVE_DIMENSIONS, judge_subjective_dimensions  # noqa: E402


def load_subjective_cases(limit: int) -> list[dict[str, Any]]:
    cases = []
    for path in sorted(BASELINE_DIR.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("expected_behavior"):
                    cases.append(row)
                if limit and len(cases) >= limit:
                    return cases
    return cases


def run_subjective_judge(limit: int) -> dict[str, Any]:
    from core.llm import llm_gateway
    import agent

    cases = load_subjective_cases(limit)
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[judge {index}/{len(cases)}] {case['id']}")
        trace = agent.get_agent_response_with_trace(case["query"], session_id=f"subjective-judge-{case['id']}")
        score = judge_subjective_dimensions(
            query=case["query"],
            response=trace.get("response", ""),
            expected_behavior=case.get("expected_behavior", ""),
            llm_gateway=llm_gateway,
        )
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "response_preview": trace.get("response", "")[:500],
                "score": score.to_dict() if score else None,
                "agent_exception": trace.get("exception"),
            }
        )

    scored = [result["score"] for result in results if result["score"]]
    summary = {
        "enabled": True,
        "dimensions": list(SUBJECTIVE_DIMENSIONS),
        "total_cases": len(results),
        "average": round(sum(score["average"] for score in scored) / len(scored), 4) if scored else 0,
        "clarity": _avg(scored, "clarity"),
        "relevance": _avg(scored, "relevance"),
        "helpfulness": _avg(scored, "helpfulness"),
        "completeness": _avg(scored, "completeness"),
    }
    return {"summary": summary, "results": results}


def skipped_subjective_judge() -> dict[str, Any]:
    return {
        "summary": {
            "enabled": False,
            "dimensions": list(SUBJECTIVE_DIMENSIONS),
            "reason": "LLM-as-a-Judge is optional and only used for subjective dimensions.",
        },
        "results": [],
    }


def _avg(scores: list[dict[str, Any]], key: str) -> float:
    return round(sum(float(score[key]) for score in scores) / len(scores), 4) if scores else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full evaluation framework aggregation.")
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--llm-judge", action="store_true", help="Run optional LLM judge for subjective dimensions.")
    parser.add_argument("--judge-limit", type=int, default=5, help="Maximum subjective judge cases when --llm-judge is set.")
    parser.add_argument("--fail-on-target", action="store_true", help="Return non-zero when deterministic targets fail.")
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    reports = load_latest_reports(report_dir)
    deterministic = deterministic_metrics_from_reports(reports)
    calibration = calibration_from_reports(reports)
    subjective = run_subjective_judge(args.judge_limit) if args.llm_judge else skipped_subjective_judge()

    report = {
        "name": "full_evaluation_framework_v1",
        "created_at": datetime.now().isoformat(),
        "report_dir": str(report_dir),
        "source_reports": sorted(reports.keys()),
        "deterministic": deterministic,
        "subjective": subjective,
        "calibration": calibration,
        "summary": {
            "deterministic_targets_pass": deterministic["all_available_targets_pass"],
            "subjective_judge_enabled": subjective["summary"]["enabled"],
            "calibrated_confidence": calibration["calibrated_confidence"],
            "confidence_band": calibration["confidence_band"],
        },
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    latest_path = report_dir / "full_evaluation_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Full evaluation framework complete.")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report saved to: {latest_path}")
    if args.fail_on_target and not deterministic["all_available_targets_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
