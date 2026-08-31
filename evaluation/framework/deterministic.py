from pathlib import Path
from typing import Any


DETERMINISTIC_DIMENSIONS = (
    "price",
    "stock",
    "sku",
    "tool",
    "arguments",
    "authorization",
    "citation",
    "schema",
    "latency",
)


def deterministic_metrics_from_reports(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic evaluation view from existing latest reports."""
    baseline = reports.get("baseline", {})
    product_search = reports.get("product_search", {})
    authorization = reports.get("authorization", {})
    rag = reports.get("rag", {})
    structured_output = reports.get("structured_output", {})
    multiturn = reports.get("multiturn", {})

    baseline_summary = baseline.get("summary", {})
    product_summary = product_search.get("summary", {})
    authorization_summary = authorization.get("summary", {})
    rag_summary = rag.get("summary", {})
    schema_summary = structured_output.get("summary", {})
    multiturn_summary = multiturn.get("summary", {})

    hard_constraint_rate = product_summary.get("hard_constraint_satisfaction")
    deterministic = {
        "dimensions": list(DETERMINISTIC_DIMENSIONS),
        "price": {
            "source": "product_search.hard_constraint_satisfaction",
            "rate": hard_constraint_rate,
            "pass": _bool_target(product_summary, "hard_constraint_satisfaction", default_threshold=0.99),
            "note": "Price is evaluated as a database-enforced hard product-search constraint.",
        },
        "stock": {
            "source": "product_search.hard_constraint_satisfaction",
            "rate": hard_constraint_rate,
            "pass": _bool_target(product_summary, "hard_constraint_satisfaction", default_threshold=0.99),
            "note": "Availability and minimum stock are evaluated as database-enforced hard constraints.",
        },
        "sku": {
            "source": "product_search.hard_constraint_satisfaction",
            "rate": hard_constraint_rate,
            "pass": _bool_target(product_summary, "hard_constraint_satisfaction", default_threshold=0.99),
            "note": "SKU is treated as a hard SQL/repository constraint when present.",
        },
        "tool": {
            "source": "baseline.tool_selection_rate",
            "rate": baseline_summary.get("tool_selection_rate"),
            "passed": baseline_summary.get("tool_selection_passed"),
            "total": baseline_summary.get("evaluated_cases"),
            "pass": _rate_at_least(baseline_summary.get("tool_selection_rate"), 0.95),
        },
        "arguments": {
            "source": "baseline.argument_accuracy_rate",
            "rate": baseline_summary.get("argument_accuracy_rate"),
            "passed": baseline_summary.get("argument_accuracy_passed"),
            "total": baseline_summary.get("evaluated_cases"),
            "pass": _rate_at_least(baseline_summary.get("argument_accuracy_rate"), 0.95),
        },
        "authorization": {
            "source": "authorization.unauthorized_successes",
            "unauthorized_successes": authorization_summary.get("unauthorized_successes"),
            "pass": authorization_summary.get("target_pass"),
        },
        "citation": {
            "source": "rag.citation_correctness",
            "rate": rag_summary.get("citation_correctness"),
            "pass": _rate_at_least(rag_summary.get("citation_correctness"), 0.99),
        },
        "schema": {
            "source": "structured_output.schema_validity_rate",
            "rate": schema_summary.get("schema_validity_rate"),
            "pass": schema_summary.get("target_pass"),
        },
        "latency": {
            "source": "baseline/product_search/rag/multiturn average latency",
            "avg_latency_ms": _avg_present(
                baseline_summary.get("avg_latency_ms"),
                product_summary.get("avg_latency_ms"),
                rag_summary.get("avg_latency_ms"),
                multiturn_summary.get("avg_latency_ms"),
            ),
            "pass": True,
            "note": "Latency is measured deterministically and threshold-free in this phase.",
        },
    }
    deterministic["all_available_targets_pass"] = all(
        value.get("pass") is not False
        for key, value in deterministic.items()
        if isinstance(value, dict) and key in DETERMINISTIC_DIMENSIONS
    )
    deterministic["missing_sources"] = _missing_sources(reports)
    return deterministic


def load_latest_reports(report_dir: Path) -> dict[str, dict[str, Any]]:
    import json

    files = {
        "baseline": "baseline_report_latest.json",
        "product_search": "product_search_report_latest.json",
        "rag": "rag_report_latest.json",
        "authorization": "authorization_report_latest.json",
        "structured_output": "structured_output_report_latest.json",
        "multiturn": "multiturn_report_latest.json",
        "security": "security_report_latest.json",
        "pii_leakage": "pii_leakage_report_latest.json",
        "hallucination": "hallucination_report_latest.json",
        "golden_validation": "golden_dataset_validation_latest.json",
    }
    reports = {}
    for name, filename in files.items():
        path = report_dir / filename
        if path.exists():
            reports[name] = json.loads(path.read_text(encoding="utf-8"))
    return reports


def _bool_target(summary: dict[str, Any], key: str, default_threshold: float) -> bool | None:
    target_pass = summary.get("target_pass")
    if isinstance(target_pass, dict) and key in target_pass:
        return bool(target_pass[key])
    return _rate_at_least(summary.get(key), default_threshold)


def _rate_at_least(value: Any, threshold: float) -> bool | None:
    if value is None:
        return None
    return float(value) >= threshold


def _avg_present(*values: Any) -> float:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 2) if present else 0


def _missing_sources(reports: dict[str, dict[str, Any]]) -> list[str]:
    required = {"baseline", "product_search", "rag", "authorization", "structured_output"}
    return sorted(required - set(reports))
