"""Compare measured candidate results; never tune production from self-reported confidence."""
from pydantic import BaseModel, ConfigDict, Field


class MeasuredRun(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    dataset_version: str = Field(min_length=1)
    samples: int = Field(ge=30)
    correct_rate: float = Field(ge=0, le=1)
    critical_failures: int = Field(ge=0)
    avg_tokens: float = Field(gt=0)
    p95_latency_ms: float = Field(gt=0)
    cost_per_correct_answer: float = Field(ge=0)


def tuning_gate(baseline, candidate):
    baseline = MeasuredRun.model_validate(baseline)
    candidate = MeasuredRun.model_validate(candidate)
    reasons = []
    if candidate.dataset_version != baseline.dataset_version or candidate.samples != baseline.samples:
        reasons.append("Evaluation datasets/sample counts differ")
    if candidate.critical_failures:
        reasons.append("Critical security or business-fact failure")
    if candidate.correct_rate < baseline.correct_rate:
        reasons.append("Quality regression")
    for field in ("avg_tokens", "p95_latency_ms", "cost_per_correct_answer"):
        before, after = getattr(baseline, field), getattr(candidate, field)
        if after > before * 1.2 and candidate.correct_rate <= baseline.correct_rate:
            reasons.append(f"{field}: increase above 20% without quality gain")
    if not (candidate.correct_rate > baseline.correct_rate or
            candidate.avg_tokens < baseline.avg_tokens or
            candidate.p95_latency_ms < baseline.p95_latency_ms or
            candidate.cost_per_correct_answer < baseline.cost_per_correct_answer):
        reasons.append("No demonstrated improvement")
    return {"eligible_for_review": not reasons, "reasons": reasons, "auto_promote": False}
