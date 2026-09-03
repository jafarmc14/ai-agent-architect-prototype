import json
import re
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "datasets" / "security" / "adversarial.jsonl"
REQUIRED_CATEGORIES = {
    "direct_injection", "indirect_injection", "authorization", "PII", "tool_abuse",
    "data_exfiltration", "system_prompt", "RAG_poisoning", "catalog_poisoning",
}


def load_cases() -> list[dict]:
    with DATASET_PATH.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate(cases: list[dict]) -> dict:
    ids = [case.get("id") for case in cases]
    queries = [case.get("query") for case in cases]
    categories = Counter(case.get("category") for case in cases)
    errors = []
    for case in cases:
        required = {"id", "category", "query", "expected_no_pii_leakage", "expected_prompt_injection_resistant"}
        missing = sorted(required - case.keys())
        if missing:
            errors.append(f"{case.get('id')}: missing {missing}")
        if re.search(r"(?:sk-[A-Za-z0-9]|password=.{4,}|JWT_SECRET=.{4,})", case.get("query", ""), re.IGNORECASE):
            errors.append(f"{case.get('id')}: possible real secret")
        if not case.get("synthetic_company_context"):
            errors.append(f"{case.get('id')}: missing synthetic company context")
    return {
        "total_cases": len(cases),
        "categories": dict(categories),
        "missing_categories": sorted(REQUIRED_CATEGORIES - set(categories)),
        "duplicate_ids": len(ids) - len(set(ids)),
        "duplicate_queries": len(queries) - len(set(queries)),
        "errors": errors,
        "target_pass": 300 <= len(cases) <= 500 and not errors and not (REQUIRED_CATEGORIES - set(categories))
        and len(ids) == len(set(ids)) and len(queries) == len(set(queries)),
    }


if __name__ == "__main__":
    report = validate(load_cases())
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["target_pass"] else 1)
