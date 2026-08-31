import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGRESSION_DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "regression" / "bugs.jsonl"


def load_existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


def parse_json_object(raw: str, field_name: str) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a bug regression case to evaluation/datasets/regression/bugs.jsonl.")
    parser.add_argument("--id", required=True, help="Stable bug case id, e.g. bug_006_refund_policy_abstain.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--expected-tool", default=None, help="Expected tool name, or omit for no-tool.")
    parser.add_argument("--expected-arguments", default="{}", help="JSON object of expected tool arguments.")
    parser.add_argument("--change-areas", default="", help="Comma-separated areas: prompt,model,embedding,retrieval,reranker,chunking,tools,business_rules,authorization.")
    parser.add_argument("--must-contain-any", default="", help="Pipe-separated response substrings; at least one should appear.")
    parser.add_argument("--must-not-contain", default="", help="Pipe-separated response substrings that must not appear.")
    parser.add_argument("--access", default="READ", choices=["READ", "WRITE"])
    parser.add_argument("--risk", default="LOW", choices=["LOW", "MEDIUM", "HIGH"])
    parser.add_argument("--introduced-by", default="bug fix")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    REGRESSION_DATASET.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = load_existing_ids(REGRESSION_DATASET)
    if args.id in existing_ids:
        raise SystemExit(f"Regression case id already exists: {args.id}")

    row = {
        "id": args.id,
        "title": args.title,
        "introduced_by": args.introduced_by,
        "change_areas": [area.strip() for area in args.change_areas.split(",") if area.strip()],
        "query": args.query,
        "expected_tool": args.expected_tool,
        "expected_arguments": parse_json_object(args.expected_arguments, "expected_arguments"),
        "assertions": {
            "response_must_contain_any": [item.strip() for item in args.must_contain_any.split("|") if item.strip()],
            "response_must_not_contain": [item.strip() for item in args.must_not_contain.split("|") if item.strip()],
        },
        "access": args.access,
        "risk": args.risk,
        "notes": args.notes,
    }
    with REGRESSION_DATASET.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Added regression case: {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
