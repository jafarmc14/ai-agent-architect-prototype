from typing import Any


def calibration_from_reports(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Estimate confidence from observable system signals, not model self-report."""
    signals = {
        "retrieval_score": _retrieval_score(reports),
        "tool_result_availability": _tool_result_availability(reports),
        "validation_outcome": _validation_outcome(reports),
        "evidence_quality": _evidence_quality(reports),
    }
    weights = {
        "retrieval_score": 0.25,
        "tool_result_availability": 0.25,
        "validation_outcome": 0.25,
        "evidence_quality": 0.25,
    }
    score = round(sum(signals[name] * weight for name, weight in weights.items()), 4)
    band = "high" if score >= 0.9 else "medium" if score >= 0.7 else "low"
    return {
        "method": "signal_based_calibration_v1",
        "do_not_use": ["self_reported_llm_confidence"],
        "signals": signals,
        "weights": weights,
        "calibrated_confidence": score,
        "confidence_band": band,
        "interpretation": (
            "Confidence is derived from retrieval/ranking metrics, tool result availability, "
            "schema/security validation outcomes, and evidence quality."
        ),
    }


def _retrieval_score(reports: dict[str, dict[str, Any]]) -> float:
    product = reports.get("product_search", {}).get("summary", {})
    rag = reports.get("rag", {}).get("summary", {})
    values = [
        product.get("precision_at_5"),
        product.get("recall_at_10"),
        product.get("ndcg_at_10"),
        rag.get("recall_at_5"),
        rag.get("precision_at_5"),
    ]
    return _avg(values)


def _tool_result_availability(reports: dict[str, dict[str, Any]]) -> float:
    baseline = reports.get("baseline", {}).get("summary", {})
    response_rate = baseline.get("response_return_rate")
    exception_rate = _exception_success_rate(baseline)
    return _avg([response_rate, exception_rate])


def _validation_outcome(reports: dict[str, dict[str, Any]]) -> float:
    structured = reports.get("structured_output", {}).get("summary", {})
    authorization = reports.get("authorization", {}).get("summary", {})
    security = reports.get("security", {}).get("summary", {})
    pii = reports.get("pii_leakage", {}).get("summary", {})
    hallucination = reports.get("hallucination", {}).get("summary", {})
    values = [
        structured.get("schema_validity_rate"),
        1.0 if authorization.get("target_pass") else 0.0 if authorization else None,
        1.0 if security.get("critical_security_failure") is False else 0.0 if security else None,
        1.0 if pii.get("target_pass") else 0.0 if pii else None,
        1.0 if hallucination.get("target_pass", {}).get("unsupported_critical_claims") else 0.0
        if hallucination else None,
    ]
    return _avg(values)


def _evidence_quality(reports: dict[str, dict[str, Any]]) -> float:
    rag = reports.get("rag", {}).get("summary", {})
    product = reports.get("product_search", {}).get("summary", {})
    values = [
        rag.get("faithfulness"),
        rag.get("citation_correctness"),
        rag.get("freshness_correctness"),
        product.get("hard_constraint_satisfaction"),
    ]
    return _avg(values)


def _exception_success_rate(summary: dict[str, Any]) -> float | None:
    total = summary.get("evaluated_cases")
    exceptions = summary.get("exceptions")
    if total is None or exceptions is None or int(total) <= 0:
        return None
    return max(0.0, 1.0 - (float(exceptions) / float(total)))


def _avg(values: list[Any]) -> float:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else 0.0
