from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.framework import calibration_from_reports, deterministic_metrics_from_reports  # noqa: E402
from evaluation.framework.subjective_judge import SUBJECTIVE_DIMENSIONS, judge_subjective_dimensions  # noqa: E402


def test_deterministic_metrics_exclude_subjective_dimensions():
    reports = {
        "baseline": {"summary": {"tool_selection_rate": 1.0, "argument_accuracy_rate": 1.0, "response_return_rate": 1.0, "evaluated_cases": 2, "exceptions": 0}},
        "product_search": {"summary": {"hard_constraint_satisfaction": 1.0, "target_pass": {"hard_constraint_satisfaction": True}}},
        "authorization": {"summary": {"unauthorized_successes": 0, "target_pass": True}},
        "rag": {"summary": {"citation_correctness": 1.0}},
        "structured_output": {"summary": {"schema_validity_rate": 1.0, "target_pass": True}},
    }
    metrics = deterministic_metrics_from_reports(reports)

    assert "tool" in metrics["dimensions"]
    assert "arguments" in metrics["dimensions"]
    assert "citation" in metrics["dimensions"]
    assert "clarity" not in metrics["dimensions"]
    assert "helpfulness" not in metrics["dimensions"]
    assert metrics["all_available_targets_pass"] is True


def test_subjective_judge_is_optional_and_limited_to_subjective_dimensions():
    assert SUBJECTIVE_DIMENSIONS == ("clarity", "relevance", "helpfulness", "completeness")
    assert judge_subjective_dimensions(query="hello", response="hi", llm_gateway=None) is None


def test_calibration_uses_observable_signals_not_self_reported_confidence():
    reports = {
        "baseline": {"summary": {"response_return_rate": 1.0, "evaluated_cases": 2, "exceptions": 0}},
        "product_search": {"summary": {"precision_at_5": 1.0, "recall_at_10": 1.0, "ndcg_at_10": 1.0, "hard_constraint_satisfaction": 1.0}},
        "rag": {"summary": {"recall_at_5": 1.0, "precision_at_5": 1.0, "faithfulness": 1.0, "citation_correctness": 1.0, "freshness_correctness": 1.0}},
        "structured_output": {"summary": {"schema_validity_rate": 1.0}},
        "authorization": {"summary": {"target_pass": True}},
        "security": {"summary": {"critical_security_failure": False}},
        "pii_leakage": {"summary": {"target_pass": True}},
        "hallucination": {"summary": {"target_pass": {"unsupported_critical_claims": True}}},
    }
    calibration = calibration_from_reports(reports)

    assert calibration["calibrated_confidence"] == 1.0
    assert calibration["confidence_band"] == "high"
    assert "self_reported_llm_confidence" in calibration["do_not_use"]
    assert sorted(calibration["signals"]) == [
        "evidence_quality",
        "retrieval_score",
        "tool_result_availability",
        "validation_outcome",
    ]


if __name__ == "__main__":
    test_deterministic_metrics_exclude_subjective_dimensions()
    test_subjective_judge_is_optional_and_limited_to_subjective_dimensions()
    test_calibration_uses_observable_signals_not_self_reported_confidence()
    print("Full evaluation framework tests passed.")
