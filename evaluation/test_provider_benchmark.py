import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.run_provider_benchmark import (  # noqa: E402
    DEFAULT_MANIFEST,
    build_comparison,
    build_plan,
    calculate_metrics,
    load_manifest,
    main,
    resolve_provider,
)


def test_manifest_builds_identical_suites_without_exposing_keys():
    manifest = load_manifest(DEFAULT_MANIFEST)
    environment = {
        "OLLAMA_MODEL": "llama3.1",
        "DEEPSEEK_MODEL": "deepseek-v4-flash",
        "DEEPSEEK_API_KEY": "secret-value",
        "KIMI_MODEL": "kimi-k2.6",
        "MOONSHOT_API_KEY": "another-secret",
    }
    plan = build_plan(
        manifest,
        ["ollama", "deepseek", "kimi"],
        Path("reports"),
        environment,
        limit_per_file=1,
    )
    command_shapes = [
        [item["dataset_file"] for item in provider["commands"]]
        for provider in plan["providers"]
    ]
    assert command_shapes[0] == command_shapes[1] == command_shapes[2]
    serialized = json.dumps(plan)
    assert "secret-value" not in serialized
    assert "another-secret" not in serialized
    assert all("--limit" in item["command"] for item in plan["providers"][0]["commands"])


def test_metric_normalization_covers_all_benchmark_dimensions():
    profile = {
        "cost_estimation_available": True,
        "input_price_per_million": 1.0,
        "output_price_per_million": 2.0,
    }
    results = [
        _result("products.jsonl", True, claims=1, unsupported=0, input_tokens=100, output_tokens=20, cost=0.01),
        _result("knowledge.jsonl", True, claims=2, unsupported=0, input_tokens=200, output_tokens=50),
        _result("orders.jsonl", False, claims=1, unsupported=1, critical=1, input_tokens=50, output_tokens=10),
    ]
    metrics = calculate_metrics(results, profile)

    assert metrics["quality_score"] == 0.6667
    assert metrics["tool_accuracy"] == 0.6667
    assert metrics["hallucination_rate"] == 0.25
    assert metrics["unsupported_critical_claims"] == 1
    assert metrics["rag_faithfulness"] == 1.0
    assert metrics["avg_latency_ms"] == 100.0
    assert metrics["total_tokens"] == 430
    assert metrics["total_cost_usd"] is not None
    assert metrics["cost_per_correct_answer"] is not None


def test_comparison_uses_correct_metric_direction():
    reports = [
        {"provider": "ollama", "metrics": {"quality_score": 0.8, "hallucination_rate": 0.0, "tool_accuracy": 0.8, "rag_faithfulness": 0.9, "avg_latency_ms": 1000, "total_tokens": 100, "total_cost_usd": 0.0, "cost_per_correct_answer": 0.0}},
        {"provider": "deepseek", "metrics": {"quality_score": 0.9, "hallucination_rate": 0.1, "tool_accuracy": 0.9, "rag_faithfulness": 1.0, "avg_latency_ms": 500, "total_tokens": 80, "total_cost_usd": 0.2, "cost_per_correct_answer": 0.01}},
    ]
    comparison = build_comparison(reports)
    assert comparison["best_by_metric"]["quality_score"] == ["deepseek"]
    assert comparison["best_by_metric"]["hallucination_rate"] == ["ollama"]
    assert comparison["best_by_metric"]["avg_latency_ms"] == ["deepseek"]
    assert comparison["best_by_metric"]["total_cost_usd"] == ["ollama"]


def test_default_cli_is_dry_run_only():
    with TemporaryDirectory() as directory:
        exit_code = main(["--report-dir", directory, "--limit-per-file", "1"])
        report = json.loads(
            (Path(directory) / "provider_benchmark_plan_latest.json").read_text(encoding="utf-8")
        )
        assert exit_code == 0
        assert report["mode"] == "dry_run"
        assert not (Path(directory) / "provider_benchmark_comparison_latest.json").exists()


def test_paid_profiles_require_credentials_and_explicit_prices():
    manifest = load_manifest(DEFAULT_MANIFEST)
    profile = resolve_provider("deepseek", manifest["providers"]["deepseek"], {})
    assert profile["credential_configured"] is False
    assert profile["cost_estimation_available"] is False


def _result(
    dataset_file: str,
    passed: bool,
    *,
    claims: int,
    unsupported: int,
    critical: int = 0,
    input_tokens: int,
    output_tokens: int,
    cost=None,
) -> dict:
    return {
        "dataset_file": dataset_file,
        "skipped": False,
        "tool_selection_pass": passed,
        "argument_accuracy_pass": passed,
        "response_returned": True,
        "exception": None,
        "latency_ms": 100,
        "citation_present": dataset_file == "knowledge.jsonl",
        "claim_audit": {
            "total_claims": claims,
            "unsupported_claim_count": unsupported,
            "unsupported_critical_claim_count": critical,
        },
        "token_usage": {
            "llm_calls": 1,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
        },
    }


if __name__ == "__main__":
    test_manifest_builds_identical_suites_without_exposing_keys()
    test_metric_normalization_covers_all_benchmark_dimensions()
    test_comparison_uses_correct_metric_direction()
    test_default_cli_is_dry_run_only()
    test_paid_profiles_require_credentials_and_explicit_prices()
    print("Provider benchmark pipeline tests passed.")
