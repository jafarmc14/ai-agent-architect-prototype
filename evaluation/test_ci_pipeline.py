import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci-quality-gate.yml"
BASELINE_PATH = PROJECT_ROOT / "evaluation" / "baselines" / "quality_baseline.json"


def _job_section(workflow: str, job: str, next_job: str | None = None) -> str:
    start = workflow.index(f"  {job}:\n")
    end = workflow.index(f"  {next_job}:\n", start) if next_job else len(workflow)
    return workflow[start:end]


def test_pipeline_has_required_ordered_gates():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    expected_dependencies = {
        "integration": "unit",
        "quality": "integration",
        "security": "quality",
        "regression": "security",
        "build": "regression",
    }

    assert "  unit:\n" in workflow
    for job, dependency in expected_dependencies.items():
        section = _job_section(workflow, job)
        assert f"    needs: {dependency}\n" in section


def test_security_is_a_hard_blocker():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    section = _job_section(workflow, "security", "regression")

    assert "run_security_evaluation.py" in section
    assert "run_pii_leakage_evaluation.py" in section
    assert "continue-on-error" not in section
    assert "if: always()" not in section.split("Upload security reports", 1)[0]


def test_quality_baseline_covers_critical_metrics():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    metrics = {metric["name"]: metric for metric in baseline["metrics"]}

    assert metrics["product_precision_at_5"]["minimum"] == 0.90
    assert metrics["product_recall_at_10"]["minimum"] == 0.95
    assert metrics["hard_constraint_satisfaction"]["minimum"] == 0.99
    assert metrics["structured_schema_validity"]["minimum"] == 0.999
    assert metrics["unsupported_critical_claims"]["maximum"] == 0


if __name__ == "__main__":
    test_pipeline_has_required_ordered_gates()
    test_security_is_a_hard_blocker()
    test_quality_baseline_covers_critical_metrics()
    print("CI pipeline contract tests passed.")
