import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASELINE_PATH = PROJECT_ROOT / "evaluation" / "baselines" / "quality_baseline.json"

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
}


def load_baseline_metrics() -> dict:
    config = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {metric["name"]: metric for metric in config["metrics"]}


def test_baseline_contains_all_phase_42_targets():
    metrics = load_baseline_metrics()
    for name, minimum in PHASE_42_TARGETS.items():
        assert name in metrics, f"missing production metric {name}"
        assert metrics[name]["minimum"] == minimum, (
            f"{name} minimum {metrics[name]['minimum']} != {minimum}"
        )
        assert metrics[name]["direction"] == "higher"


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
    metrics = load_baseline_metrics()
    schema = metrics["structured_schema_validity"]
    assert schema["minimum"] == 0.999
    assert evaluate_metric(schema, 0.999)["pass"] is True
    assert evaluate_metric(schema, 0.998)["pass"] is False


if __name__ == "__main__":
    test_baseline_contains_all_phase_42_targets()
    test_higher_metric_passes_at_exact_threshold()
    test_argument_accuracy_requires_99_percent()
    test_schema_validity_requires_999_percent()
    print("Production quality gate tests passed.")
