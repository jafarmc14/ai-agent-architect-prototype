import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "evaluation" / "provider_benchmark.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports" / "provider_benchmark"
BASELINE_DATASET_DIR = PROJECT_ROOT / "evaluation" / "datasets" / "baseline"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.run_baseline import summarize as summarize_baseline  # noqa: E402


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError("Unsupported provider benchmark manifest version.")
    if not manifest.get("dataset_files") or not manifest.get("providers"):
        raise ValueError("Benchmark manifest requires dataset_files and providers.")
    return manifest


def resolve_provider(name: str, raw: dict[str, Any], environment: dict[str, str]) -> dict[str, Any]:
    key_envs = list(raw.get("api_key_envs") or [])
    input_price = _price(raw.get("input_price_env"), raw.get("default_input_price_per_million"), environment)
    output_price = _price(raw.get("output_price_env"), raw.get("default_output_price_per_million"), environment)
    return {
        **raw,
        "name": name,
        "model": environment.get(raw["model_env"]) or raw["default_model"],
        "credential_configured": not key_envs or any(environment.get(key) for key in key_envs),
        "input_price_per_million": input_price,
        "output_price_per_million": output_price,
        "cost_estimation_available": input_price is not None and output_price is not None,
    }


def build_plan(
    manifest: dict[str, Any],
    provider_names: list[str],
    report_root: Path,
    environment: dict[str, str],
    limit_per_file: int = 0,
) -> dict[str, Any]:
    plans = []
    for name in provider_names:
        if name not in manifest["providers"]:
            raise ValueError(f"Unknown benchmark provider: {name}")
        profile = resolve_provider(name, manifest["providers"][name], environment)
        commands = []
        for dataset_file in manifest["dataset_files"]:
            file_report_dir = report_root / name / "parts" / dataset_file
            command = [
                sys.executable,
                "evaluation/run_baseline.py",
                "--dataset-dir", str(BASELINE_DATASET_DIR),
                "--report-dir", str(file_report_dir),
                "--files", dataset_file,
            ]
            if limit_per_file > 0:
                command.extend(["--limit", str(limit_per_file)])
            commands.append({"dataset_file": dataset_file, "command": command, "report_dir": str(file_report_dir)})
        plans.append({
            "provider": name,
            "model": profile["model"],
            "paid": bool(profile.get("paid")),
            "credential_configured": profile["credential_configured"],
            "cost_estimation_available": profile["cost_estimation_available"],
            "commands": commands,
        })
    return {"providers": plans, "dataset_files": list(manifest["dataset_files"])}


def calculate_metrics(results: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    evaluated = [result for result in results if not result.get("skipped")]
    correct_answers = 0
    total_claims = unsupported_claims = unsupported_critical = 0
    rag_faithfulness = []
    input_tokens = output_tokens = 0
    known_cost = 0.0
    cost_available = True

    for result in evaluated:
        audit = result.get("claim_audit") or {}
        claims = int(audit.get("total_claims") or 0)
        unsupported = int(audit.get("unsupported_claim_count") or 0)
        critical = int(audit.get("unsupported_critical_claim_count") or 0)
        total_claims += claims
        unsupported_claims += unsupported
        unsupported_critical += critical
        usage = result.get("token_usage") or {}
        case_input = int(usage.get("input_tokens") or 0)
        case_output = int(usage.get("output_tokens") or 0)
        input_tokens += case_input
        output_tokens += case_output
        case_cost = usage.get("cost_usd")
        if case_cost is None and int(usage.get("llm_calls") or 0) == 0:
            case_cost = 0.0
        if case_cost is None and profile["cost_estimation_available"]:
            case_cost = (
                case_input * profile["input_price_per_million"]
                + case_output * profile["output_price_per_million"]
            ) / 1_000_000
        if case_cost is None:
            cost_available = False
        else:
            known_cost += float(case_cost)

        if result.get("dataset_file") == "knowledge.jsonl":
            if claims:
                rag_faithfulness.append(max(0.0, 1 - unsupported / claims))
            else:
                rag_faithfulness.append(1.0 if result.get("citation_present") else 0.0)

        if (
            result.get("tool_selection_pass")
            and result.get("argument_accuracy_pass")
            and result.get("response_returned")
            and not result.get("exception")
            and critical == 0
        ):
            correct_answers += 1

    count = len(evaluated)
    tool_selection = _rate(evaluated, "tool_selection_pass")
    argument_accuracy = _rate(evaluated, "argument_accuracy_pass")
    tool_accuracy = round((tool_selection + argument_accuracy) / 2, 4) if count else 0.0
    total_cost = round(known_cost, 10) if cost_available else None
    return {
        "evaluated_cases": count,
        "correct_answers": correct_answers,
        "quality_score": round(correct_answers / count, 4) if count else 0.0,
        "tool_selection_rate": tool_selection,
        "argument_accuracy_rate": argument_accuracy,
        "tool_accuracy": tool_accuracy,
        "hallucination_rate": round(unsupported_claims / total_claims, 4) if total_claims else 0.0,
        "unsupported_critical_claims": unsupported_critical,
        "claims_evaluated": total_claims,
        "rag_faithfulness": round(sum(rag_faithfulness) / len(rag_faithfulness), 4) if rag_faithfulness else None,
        "rag_cases_evaluated": len(rag_faithfulness),
        "avg_latency_ms": round(sum(float(item.get("latency_ms") or 0) for item in evaluated) / count, 2) if count else 0.0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "avg_tokens_per_case": round((input_tokens + output_tokens) / count, 2) if count else 0.0,
        "total_cost_usd": total_cost,
        "cost_per_correct_answer": round(total_cost / correct_answers, 10) if total_cost is not None and correct_answers else None,
        "cost_estimation_available": cost_available,
    }


def build_comparison(provider_reports: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {report["provider"]: report["metrics"] for report in provider_reports}
    directions = {
        "quality_score": "max",
        "hallucination_rate": "min",
        "tool_accuracy": "max",
        "rag_faithfulness": "max",
        "avg_latency_ms": "min",
        "total_tokens": "min",
        "total_cost_usd": "min",
        "cost_per_correct_answer": "min",
    }
    winners = {}
    for metric, direction in directions.items():
        available = {name: values.get(metric) for name, values in metrics.items() if values.get(metric) is not None}
        if not available:
            winners[metric] = None
            continue
        target = (max if direction == "max" else min)(available.values())
        winners[metric] = sorted(name for name, value in available.items() if value == target)
    return {"providers": metrics, "best_by_metric": winners, "metric_directions": directions}


def execute_provider(profile, provider_plan, report_root: Path, base_environment: dict[str, str]) -> dict[str, Any]:
    provider_dir = report_root / profile["name"]
    benchmark_db = provider_dir / "benchmark.db"
    environment = dict(base_environment)
    environment.update({
        "APP_ENV": "testing",
        "LLM_PROVIDER": profile["provider"],
        profile["model_env"]: profile["model"],
        "PROVIDER_BENCHMARK_MODE": "true",
        "BENCHMARK_DATABASE_PROVIDER": "sqlite",
        "BENCHMARK_DATABASE_PATH": str(benchmark_db),
        "MAX_INPUT_PRICE_PER_MILLION": str(profile["input_price_per_million"] or 0),
        "MAX_OUTPUT_PRICE_PER_MILLION": str(profile["output_price_per_million"] or 0),
    })
    part_reports = []
    commands = provider_plan["commands"]
    for index, item in enumerate(commands, start=1):
        print(f"[{profile['name']} {index}/{len(commands)}] {item['dataset_file']}")
        completed = subprocess.run(
            item["command"], cwd=PROJECT_ROOT, env=environment,
            capture_output=True, text=True, check=False,
        )
        if completed.stdout:
            print(completed.stdout.rstrip())
        if completed.returncode != 0:
            raise RuntimeError(
                f"Benchmark command failed for {profile['name']}/{item['dataset_file']}: "
                f"{completed.stderr[-1000:]}"
            )
        report_path = Path(item["report_dir"]) / "baseline_report_latest.json"
        part_reports.append(json.loads(report_path.read_text(encoding="utf-8")))

    results = [result for report in part_reports for result in report.get("results", [])]
    provider_report = {
        "provider": profile["name"],
        "model": profile["model"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_summary": summarize_baseline(results),
        "metrics": calculate_metrics(results, profile),
        "results": results,
    }
    provider_dir.mkdir(parents=True, exist_ok=True)
    (provider_dir / "provider_report_latest.json").write_text(
        json.dumps(provider_report, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return provider_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark identical agent cases across LLM providers.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--providers", nargs="*", default=["ollama", "deepseek", "kimi"])
    parser.add_argument("--limit-per-file", type=int, default=0)
    parser.add_argument("--execute", action="store_true", help="Actually invoke selected providers. Default is dry-run.")
    parser.add_argument("--confirm-paid", action="store_true", help="Required with --execute when paid providers are selected.")
    args = parser.parse_args(argv)

    from configs import get_settings
    get_settings()  # Load local environment files into os.environ without printing secrets.

    manifest = load_manifest(Path(args.manifest))
    report_root = Path(args.report_dir)
    unknown_providers = [name for name in args.providers if name not in manifest["providers"]]
    if unknown_providers:
        parser.error(f"Unknown benchmark provider(s): {', '.join(unknown_providers)}")
    profiles = [resolve_provider(name, manifest["providers"][name], os.environ) for name in args.providers]
    plan = build_plan(manifest, args.providers, report_root, os.environ, args.limit_per_file)
    plan_report = {
        "name": "provider_benchmark_plan_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "execute" if args.execute else "dry_run",
        **plan,
    }
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "provider_benchmark_plan_latest.json").write_text(
        json.dumps(plan_report, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    if not args.execute:
        print(json.dumps(plan_report, indent=2, ensure_ascii=False))
        print("Dry run only. No provider request was made.")
        return 0

    missing = [profile["name"] for profile in profiles if not profile["credential_configured"]]
    if missing:
        print(f"Missing provider credentials: {', '.join(missing)}", file=sys.stderr)
        return 2
    if any(profile.get("paid") for profile in profiles) and not args.confirm_paid:
        print("--confirm-paid is required before executing paid provider benchmarks.", file=sys.stderr)
        return 2

    provider_reports = [
        execute_provider(profile, provider_plan, report_root, os.environ)
        for profile, provider_plan in zip(profiles, plan["providers"])
    ]
    comparison = {
        "name": "provider_benchmark_comparison_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "comparison": build_comparison(provider_reports),
    }
    output = report_root / "provider_benchmark_comparison_latest.json"
    output.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(comparison["comparison"], indent=2, ensure_ascii=False))
    print(f"Comparison saved to: {output}")
    return 0


def _price(env_name: str | None, default: Any, environment: dict[str, str]) -> float | None:
    value = environment.get(env_name) if env_name else default
    if value in (None, ""):
        return None
    parsed = float(value)
    if parsed < 0:
        raise ValueError("Benchmark token prices cannot be negative.")
    return parsed


def _rate(results: list[dict[str, Any]], key: str) -> float:
    return round(sum(bool(item.get(key)) for item in results) / len(results), 4) if results else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
