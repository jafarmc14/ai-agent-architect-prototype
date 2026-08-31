from dataclasses import asdict, dataclass
from typing import Any


SUBJECTIVE_DIMENSIONS = ("clarity", "relevance", "helpfulness", "completeness")


@dataclass(frozen=True)
class SubjectiveJudgeScore:
    clarity: float
    relevance: float
    helpfulness: float
    completeness: float
    rationale: str
    judge_model: str = ""

    @property
    def average(self) -> float:
        return round((self.clarity + self.relevance + self.helpfulness + self.completeness) / 4, 4)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["average"] = self.average
        return data


def judge_subjective_dimensions(
    *,
    query: str,
    response: str,
    expected_behavior: str = "",
    llm_gateway: Any | None = None,
) -> SubjectiveJudgeScore | None:
    """Use LLM-as-a-Judge only for subjective answer-quality dimensions."""
    if llm_gateway is None:
        return None

    schema = {
        "type": "object",
        "properties": {
            "clarity": {"type": "number", "minimum": 0, "maximum": 1},
            "relevance": {"type": "number", "minimum": 0, "maximum": 1},
            "helpfulness": {"type": "number", "minimum": 0, "maximum": 1},
            "completeness": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
        },
        "required": ["clarity", "relevance", "helpfulness", "completeness", "rationale"],
        "additionalProperties": False,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are an evaluation judge. Score only subjective answer quality: "
                "clarity, relevance, helpfulness, and completeness. Do not score factual correctness, "
                "tool use, authorization, citations, schema validity, or latency."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Query:\n{query}\n\n"
                f"Expected behavior:\n{expected_behavior}\n\n"
                f"Assistant response:\n{response}\n\n"
                "Return JSON scores from 0 to 1."
            ),
        },
    ]
    payload = llm_gateway.generate_structured_sync(messages=messages, schema=schema, temperature=0)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    return SubjectiveJudgeScore(
        clarity=float(payload.get("clarity", 0)),
        relevance=float(payload.get("relevance", 0)),
        helpfulness=float(payload.get("helpfulness", 0)),
        completeness=float(payload.get("completeness", 0)),
        rationale=str(payload.get("rationale", ""))[:500],
        judge_model=getattr(llm_gateway, "model", "") or "",
    )
