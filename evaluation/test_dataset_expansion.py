import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_functional_dataset_meets_phase_41_target():
    golden = ROOT / "evaluation" / "datasets" / "golden"
    rows = [row for path in golden.glob("*.jsonl") for row in _rows(path)]
    assert 1000 <= len(rows) <= 2000
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({row["query"] for row in rows}) == len(rows)
    assert sum(row.get("category") == "company_operations" for row in rows) >= 200


def test_adversarial_dataset_meets_phase_41_target():
    rows = _rows(ROOT / "evaluation" / "datasets" / "security" / "adversarial.jsonl")
    assert 300 <= len(rows) <= 500
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({row["query"] for row in rows}) == len(rows)
    assert len({row["category"] for row in rows}) == 9
    assert all(row.get("synthetic_company_context") is True for row in rows)


if __name__ == "__main__":
    test_functional_dataset_meets_phase_41_target()
    test_adversarial_dataset_meets_phase_41_target()
    print("Dataset expansion tests passed.")
