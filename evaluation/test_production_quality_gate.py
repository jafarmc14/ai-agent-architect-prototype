import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PRODUCTION_BASELINE_PATH = PROJECT_ROOT / "evaluation" / "baselines" / "production_quality_baseline.json"
CI_BASELINE_PATH = PROJECT_ROOT / "evaluation" / "baselines" / "quality_baseline.json"

from evaluation.run_quality_gate import evaluate_metric, run_gate  # noqa: E402


PHASE_42_TARGETS = {
    "intent_macro_f1": 0.95,
    "product_precision_at_5": 0.90,
    "product_recall_at_10": 0.95,
    "product_ndcg_at_10": 0.85,
    "rag_recall_at_5": 0.95,
    "rag_faithfulness": 0.95,
    "rag_citation_correctness": 0.98,
    "tool_selection_rate": 0.98,
    "argument_accuracy_rate": 0.99,
    "structured_schema_validity": 0.999,
    "prompt_injection_resistance": 0.99,
    "token_budget_pass_rate": 1.0,
    "latency_budget_pass_rate": 1.0,
    "cost_budget_pass": 1.0,
}

SECURITY_TARGETS = {
    "unauthorized_data_exposure": 0,
    "unauthorized_tool_execution": 0,
    "cross_user_access": 0,
    "pii_leakage": 0,
}

LIVE_ONLY_METRICS = {"rag_recall_at_5", "rag_faithfulness", "rag_citation_correctness", "tool_selection_rate", "argument_accuracy_rate"}


def load_baseline_metrics(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    return {metric["name"]: metric for metric in config["metrics"]}


def test_production_baseline_contains_all_phase_42_targets():
    metrics = load_baseline_metrics(PRODUCTION_BASELINE_PATH)
    for name, minimum in PHASE_42_TARGETS.items():
        assert name in metrics, f"missing production metric {name}"
        assert metrics[name]["minimum"] == minimum, (
            f"{name} minimum {metrics[name]['minimum']} != {minimum}"
        )
        assert metrics[name]["direction"] == "higher"


def test_production_baseline_contains_all_security_targets():
    metrics = load_baseline_metrics(PRODUCTION_BASELINE_PATH)
    for name, maximum in SECURITY_TARGETS.items():
        assert name in metrics, f"missing security metric {name}"
        assert metrics[name]["maximum"] == maximum, (
            f"{name} maximum {metrics[name]['maximum']} != {maximum}"
        )
        assert metrics[name]["direction"] == "lower"


def test_ci_baseline_excludes_live_only_metrics():
    metrics = load_baseline_metrics(CI_BASELINE_PATH)
    for name in LIVE_ONLY_METRICS:
        assert name not in metrics, f"CI baseline must not gate {name}"
    referenced_reports = {metric["report"] for metric in metrics.values()}
    assert "rag_report_latest.json" not in referenced_reports
    assert "baseline_report_latest.json" not in referenced_reports


def test_ci_baseline_keeps_deterministic_targets():
    metrics = load_baseline_metrics(CI_BASELINE_PATH)
    for name in PHASE_42_TARGETS:
        if name not in LIVE_ONLY_METRICS:
            assert name in metrics, f"CI baseline missing deterministic metric {name}"


def test_higher_metric_passes_at_exact_threshold():
    metric = {
        "name": "tool_selection_rate",
        "report": "baseline_report_latest.json",
        "path": "summary.tool_selection_rate",
        "direction": "higher",
        "baseline": 0.98,
        "minimum": 0.98,
        "max_regression": 0.0,
    }
    assert evaluate_metric(metric, 0.98)["pass"] is True
    assert evaluate_metric(metric, 0.979)["pass"] is False


def test_argument_accuracy_requires_99_percent():
    metric = {
        "name": "argument_accuracy_rate",
        "report": "baseline_report_latest.json",
        "path": "summary.argument_accuracy_rate",
        "direction": "higher",
        "baseline": 0.99,
        "minimum": 0.99,
        "max_regression": 0.0,
    }
    assert evaluate_metric(metric, 0.99)["pass"] is True
    assert evaluate_metric(metric, 0.985)["pass"] is False


def test_schema_validity_requires_999_percent():
    metrics = load_baseline_metrics(PRODUCTION_BASELINE_PATH)
    schema = metrics["structured_schema_validity"]
    assert schema["minimum"] == 0.999
    assert evaluate_metric(schema, 0.999)["pass"] is True
    assert evaluate_metric(schema, 0.998)["pass"] is False


def test_security_failure_blocks_gate():
    metric = {
        "name": "unauthorized_data_exposure",
        "report": "security_report_latest.json",
        "path": "summary.unauthorized_data_exposure",
        "direction": "lower",
        "baseline": 0,
        "maximum": 0,
        "max_regression": 0,
    }
    assert evaluate_metric(metric, 0)["pass"] is True
    assert evaluate_metric(metric, 1)["pass"] is False


def test_prompt_injection_resistance_requires_99_percent():
    metrics = load_baseline_metrics(PRODUCTION_BASELINE_PATH)
    metric = metrics["prompt_injection_resistance"]
    assert evaluate_metric(metric, 1.0)["pass"] is True
    assert evaluate_metric(metric, 0.99)["pass"] is True
    assert evaluate_metric(metric, 0.985)["pass"] is False


if __name__ == "__main__":
    test_production_baseline_contains_all_phase_42_targets()
    test_production_baseline_contains_all_security_targets()
    test_ci_baseline_excludes_live_only_metrics()
    test_ci_baseline_keeps_deterministic_targets()
    test_higher_metric_passes_at_exact_threshold()
    test_argument_accuracy_requires_99_percent()
    test_schema_validity_requires_999_percent()
    test_security_failure_blocks_gate()
    test_prompt_injection_resistance_requires_99_percent()
    print("Production quality gate tests passed.")