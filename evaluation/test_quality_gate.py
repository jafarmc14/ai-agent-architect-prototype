import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.run_quality_gate import evaluate_metric, nested_value, run_gate  # noqa: E402


def test_nested_value_reads_metric_path():
    assert nested_value({"summary": {"score": 0.97}}, "summary.score") == 0.97


def test_higher_metric_enforces_absolute_and_regression_limits():
    metric = {
        "name": "score",
        "report": "candidate.json",
        "path": "summary.score",
        "direction": "higher",
        "baseline": 0.98,
        "minimum": 0.90,
        "max_regression": 0.02,
    }
    assert evaluate_metric(metric, 0.96)["pass"] is True
    assert evaluate_metric(metric, 0.959)["pass"] is False


def test_lower_metric_is_a_hard_blocker():
    metric = {
        "name": "critical_failures",
        "report": "candidate.json",
        "path": "summary.failures",
        "direction": "lower",
        "baseline": 0,
        "maximum": 0,
        "max_regression": 0,
    }
    assert evaluate_metric(metric, 0)["pass"] is True
    assert evaluate_metric(metric, 1)["pass"] is False


def test_gate_fails_on_missing_report_and_regression():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        baseline_path = root / "baseline.json"
        report_dir = root / "reports"
        report_dir.mkdir()
        baseline_path.write_text(
            json.dumps({
                "metrics": [
                    {
                        "name": "quality",
                        "report": "quality.json",
                        "path": "summary.score",
                        "direction": "higher",
                        "baseline": 1.0,
                        "minimum": 0.9,
                        "max_regression": 0.01,
                    },
                    {
                        "name": "missing",
                        "report": "missing.json",
                        "path": "summary.score",
                        "direction": "higher",
                        "baseline": 1.0,
                        "minimum": 0.9,
                        "max_regression": 0.01,
                    },
                ]
            }),
            encoding="utf-8",
        )
        (report_dir / "quality.json").write_text(
            json.dumps({"summary": {"score": 0.95}}),
            encoding="utf-8",
        )

        report = run_gate(baseline_path, report_dir)

        assert report["summary"]["pass"] is False
        assert report["summary"]["quality_regression_blocked"] is True
        assert len(report["errors"]) == 1
        assert report["results"][0]["pass"] is False


if __name__ == "__main__":
    test_nested_value_reads_metric_path()
    test_higher_metric_enforces_absolute_and_regression_limits()
    test_lower_metric_is_a_hard_blocker()
    test_gate_fails_on_missing_report_and_regression()
    print("Quality gate tests passed.")
