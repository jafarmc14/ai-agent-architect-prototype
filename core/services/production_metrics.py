"""Pure calculations; proxy signals are kept separate from reviewed correctness."""
import hashlib
import json
import math
import re
from collections import Counter
from statistics import mean


def language_bucket(text):
    words = set(re.findall(r"[a-z]+", text.lower()))
    indonesian = len(words & {"saya", "tolong", "berapa", "apakah", "sepatu", "pesanan", "barang", "bisa", "yang"})
    english = len(words & {"the", "what", "find", "please", "shoes", "order", "is", "can", "my"})
    return "id" if indonesian > english else "en" if english > indonesian else "unknown"


def capture_metrics(text, trace):
    audit = trace.get("claim_audit") or {}
    calls = trace.get("tool_calls") or []
    return {
        "llm_calls": sum(event.get("stage") == "llm" and event.get("name") in {"llm.generate", "llm.generate_structured"}
                         for event in trace.get("lifecycle", [])),
        "intent": trace.get("intent") or "UNKNOWN",
        "language_heuristic": language_bucket(text),
        "query_length_bucket": "short" if len(text) < 80 else "medium" if len(text) < 300 else "long",
        "abstained": bool(trace.get("hallucination_abstained")) or any(
            c.get("name") == "search_knowledge_base" and "Retrieval behavior: abstain." in str(c.get("output", "")) for c in calls),
        "escalated": any(c.get("name") == "escalate_to_human" and "created successfully" in str(c.get("output", "")) for c in calls),
        "tool_validations": [bool(c["validation_pass"]) for c in calls if "validation_pass" in c],
        "claim_support_proxy": (1 - audit["unsupported_claim_rate"]) if audit.get("total_claims", 0) > 0 else None,
        "unsupported_critical_claims": audit.get("unsupported_critical_claim_count"),
        "experiment": trace.get("experiment"),
    }


def average(values):
    known = [float(v) for v in values if v is not None]
    return mean(known) if known else None


def relative_drift(previous, current):
    if previous is None or current is None:
        return None
    if previous == 0:
        return 0.0 if current == 0 else None
    return (current - previous) / previous


def distribution_drift(left, right):
    a, b = Counter(left), Counter(right)
    if not a or not b:
        return None
    divergence = 0.0
    for key in a.keys() | b.keys():
        p, q = a[key] / sum(a.values()), b[key] / sum(b.values())
        midpoint = (p + q) / 2
        divergence += (p * math.log2(p / midpoint) if p else 0) / 2
        divergence += (q * math.log2(q / midpoint) if q else 0) / 2
    return divergence


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def summarize(rows):
    reviews = [r["review"] for r in rows if r.get("review")]
    ratings = [r["negative_feedback"] for r in rows if r.get("negative_feedback") is not None]
    validations = [v for r in rows for v in r["metrics"].get("tool_validations", [])]
    return {
        "requests": len(rows), "reviewed_requests": len(reviews), "rated_requests": len(ratings),
        "faithfulness": average(r.get("faithfulness") for r in reviews),
        "tool_accuracy": average(r.get("tool_accuracy") for r in reviews),
        "claim_support_proxy": average(r["metrics"].get("claim_support_proxy") for r in rows),
        "tool_validation_rate": average(validations),
        "abstention_rate": average(r["metrics"].get("abstained") for r in rows),
        "escalation_rate": average(r["metrics"].get("escalated") for r in rows),
        "negative_feedback_rate": average(ratings),
        "avg_tokens": average(r.get("tokens") for r in rows),
        "avg_latency_ms": average(r.get("latency_ms") for r in rows),
        "avg_cost_usd": average(r.get("cost_usd") for r in rows),
        "unknown_token_requests": sum(r.get("tokens") is None for r in rows),
        "unknown_cost_requests": sum(r.get("cost_usd") is None for r in rows),
        "error_rate": average(r.get("status") == "error" for r in rows),
    }


def monitoring_report(previous, current, min_samples=30):
    before, after = summarize(previous), summarize(current)
    enough = len(previous) >= min_samples and len(current) >= min_samples
    drift = {key: relative_drift(before[key], after[key]) for key in ("avg_tokens", "avg_latency_ms", "avg_cost_usd")}
    distributions = {key: distribution_drift([r["metrics"].get(key, "unknown") for r in previous],
                                            [r["metrics"].get(key, "unknown") for r in current])
                     for key in ("intent", "language_heuristic", "query_length_bucket")}
    alerts = []
    if enough:
        alerts += [key for key, value in drift.items() if value is not None and value > .20]
        alerts += [key for key, value in distributions.items() if value is not None and value > .10]
        if before["avg_cost_usd"] == 0 and (after["avg_cost_usd"] or 0) > 0:
            alerts.append("cost_increased_from_zero")
        for key in ("faithfulness", "tool_accuracy"):
            if min(before["reviewed_requests"], after["reviewed_requests"]) >= min_samples and before[key] is not None and after[key] is not None and before[key] - after[key] > .05:
                alerts.append(key)
        for key in ("negative_feedback_rate", "abstention_rate", "escalation_rate"):
            if key == "negative_feedback_rate" and min(before["rated_requests"], after["rated_requests"]) < min_samples:
                continue
            if before[key] is not None and after[key] is not None and after[key] - before[key] > .05:
                alerts.append(key)
    by_day = {}
    for row in current:
        if row.get("created_at"):
            by_day.setdefault(str(row["created_at"].date()), []).append(row)
    return {"baseline": before, "current": after, "daily": {day: summarize(rows) for day, rows in by_day.items()},
            "relative_drift": drift, "distribution_js_divergence": distributions,
            "status": "insufficient_data" if not enough else "alert" if alerts else "stable", "alerts": alerts}


def wilson(successes, total):
    if not total:
        return (0., 1.)
    z = 1.96
    p = successes / total
    center = (p + z*z/(2*total)) / (1+z*z/total)
    radius = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / (1+z*z/total)
    return center-radius, center+radius


def promotion_gate(rows, experiment_id, min_users=100):
    arms = {arm: [r for r in rows if (r["metrics"].get("experiment") or {}).get("id") == experiment_id
                 and (r["metrics"].get("experiment") or {}).get("mode") == "ab"
                 and (r["metrics"].get("experiment") or {}).get("arm") == arm] for arm in ("control", "candidate")}
    reasons, intervals = [], {}
    configurations = {fingerprint({key: (r["metrics"].get("experiment") or {}).get(key)
                                   for key in ("candidate_provider", "candidate_model", "control_provider", "control_model", "prompt", "percentage")})
                      for samples in arms.values() for r in samples}
    if len(configurations) > 1:
        reasons.append("Experiment configuration or prompt changed; start a new experiment ID")
    for arm, samples in arms.items():
        # Assignment is per user: collapse repeated requests to avoid pseudo-replication.
        grouped = {}
        for row in samples:
            grouped.setdefault(row["user_id"], []).append(row)
        outcomes = []
        for user_rows in grouped.values():
            reviews = [r.get("review") for r in user_rows]
            if not all(review and review.get("correct") is not None and review.get("critical_failure") is not None
                       and review.get("faithfulness") is not None for review in reviews):
                reasons.append(f"{arm}: incomplete reviewed quality")
                continue
            outcomes.append(all(r["correct"] and not r["critical_failure"] for r in reviews))
            if any(r["critical_failure"] for r in reviews):
                reasons.append(f"{arm}: critical failure")
        if len(outcomes) < min_users:
            reasons.append(f"{arm}: fewer than {min_users} reviewed users")
        intervals[arm] = wilson(sum(outcomes), len(outcomes))
        if any(r.get("cost_usd") is None or r.get("tokens") is None or r.get("latency_ms") is None for r in samples):
            reasons.append(f"{arm}: incomplete cost/token/latency accounting")
        if any((r["metrics"].get("experiment") or {}).get("contaminated") for r in samples):
            reasons.append(f"{arm}: fallback or model configuration changed")
        if any((r["metrics"].get("experiment") or {}).get("raw_quality_proxy", {}).get("unsupported_critical_claims", 0) for r in samples):
            reasons.append(f"{arm}: unsupported critical claim detected")
    if intervals["candidate"][0] <= intervals["control"][1]:
        reasons.append("Quality improvement is not demonstrated by non-overlapping 95% user-level Wilson intervals")
    control, candidate = summarize(arms["control"]), summarize(arms["candidate"])
    if min(control["rated_requests"], candidate["rated_requests"]) < 30:
        reasons.append("At least 30 rated requests per arm are required")
    for key in ("negative_feedback_rate", "escalation_rate", "abstention_rate", "error_rate"):
        if control[key] is not None and candidate[key] is not None and candidate[key] > control[key] + .05:
            reasons.append(f"{key}: candidate exceeds 5 percentage point regression budget")
    for key in ("faithfulness", "tool_accuracy"):
        if control[key] is not None and candidate[key] is not None and candidate[key] < control[key]:
            reasons.append(f"{key}: quality regression")
    for key in ("avg_tokens", "avg_latency_ms", "avg_cost_usd"):
        if control[key] is not None and candidate[key] is not None and candidate[key] > control[key] * 1.20:
            reasons.append(f"{key}: candidate exceeds 20% regression budget")
    return {"promotable": not reasons, "reasons": sorted(set(reasons)), "quality_intervals": intervals,
            "control": control, "candidate": candidate, "automatic_promotion": False}
