import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "evaluation" / "datasets" / "golden"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

REQUIRED_FILES = {
    "standard.jsonl",
    "ambiguous.jsonl",
    "multilingual.jsonl",
    "noisy.jsonl",
    "no_answer.jsonl",
    "cross_turn.jsonl",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["_file"] = path.name
            row["_line"] = line_number
            rows.append(row)
    return rows


def validate_case(row: dict[str, Any]) -> list[str]:
    errors = []
    for key in ("id", "query", "expected_arguments", "access", "risk"):
        if key not in row:
            errors.append(f"missing {key}")
    if not isinstance(row.get("id"), str) or not row.get("id"):
        errors.append("id must be a non-empty string")
    if not isinstance(row.get("query"), str) or not row.get("query"):
        errors.append("query must be a non-empty string")
    if row.get("expected_tool") is not None and not isinstance(row.get("expected_tool"), (str, list)):
        errors.append("expected_tool must be null, string, or list")
    if not isinstance(row.get("expected_arguments"), (dict, list)):
        errors.append("expected_arguments must be an object or list")
    if row.get("_file") == "cross_turn.jsonl":
        if not isinstance(row.get("turns"), list) or len(row.get("turns", [])) < 2:
            errors.append("cross-turn case must include at least two turns")
        if "expected_state" not in row:
            errors.append("cross-turn case must include expected_state")
    return errors


def main() -> int:
    missing_files = sorted(REQUIRED_FILES - {path.name for path in DATASET_DIR.glob("*.jsonl")})
    rows = []
    for path in sorted(DATASET_DIR.glob("*.jsonl")):
        rows.extend(load_jsonl(path))

    ids = {}
    duplicate_ids = []
    case_errors = []
    for row in rows:
        row_id = row.get("id")
        if row_id in ids:
            duplicate_ids.append(row_id)
        ids[row_id] = True
        errors = validate_case(row)
        for error in errors:
            case_errors.append(f"{row.get('_file')}:{row.get('_line')} {row_id}: {error}")

    counts_by_file = {}
    counts_by_category = {}
    for row in rows:
        counts_by_file[row["_file"]] = counts_by_file.get(row["_file"], 0) + 1
        category = row.get("category") or row["_file"].replace(".jsonl", "")
        counts_by_category[category] = counts_by_category.get(category, 0) + 1

    total_cases = len(rows)
    target_pass = 450 <= total_cases <= 550 and not missing_files and not duplicate_ids and not case_errors
    report = {
        "name": "golden_dataset_validation_v1",
        "dataset_dir": str(DATASET_DIR),
        "total_cases": total_cases,
        "target_case_count_range": "450-550",
        "counts_by_file": counts_by_file,
        "counts_by_category": counts_by_category,
        "missing_files": missing_files,
        "duplicate_ids": duplicate_ids,
        "case_errors": case_errors,
        "target_pass": target_pass,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = REPORT_DIR / "golden_dataset_validation_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if target_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
