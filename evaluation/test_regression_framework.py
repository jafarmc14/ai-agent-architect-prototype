from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.run_regression import (  # noqa: E402
    CHANGE_AREA_COMMANDS,
    DEFAULT_AREAS,
    evaluate_response_assertions,
    load_bug_cases,
    validate_bug_cases,
)


def test_every_required_change_area_has_regression_commands():
    for area in DEFAULT_AREAS:
        assert area in CHANGE_AREA_COMMANDS
        assert CHANGE_AREA_COMMANDS[area]


def test_bug_regression_dataset_is_valid():
    cases = load_bug_cases(PROJECT_ROOT / "evaluation" / "datasets" / "regression" / "bugs.jsonl")
    validation = validate_bug_cases(cases, set(DEFAULT_AREAS))

    assert validation["pass"] is True
    assert validation["total_cases"] >= 5
    assert validation["errors"] == []


def test_response_assertions_support_positive_and_negative_checks():
    assertions = {
        "response_must_contain_any": ["support ticket", "human agent"],
        "response_must_not_contain": ["not enough verified evidence"],
    }
    result = evaluate_response_assertions("Support ticket #ABC created successfully.", assertions)
    assert result["pass"] is True

    failed = evaluate_response_assertions("Sorry, not enough verified evidence.", assertions)
    assert failed["pass"] is False
    assert failed["errors"]


if __name__ == "__main__":
    test_every_required_change_area_has_regression_commands()
    test_bug_regression_dataset_is_valid()
    test_response_assertions_support_positive_and_negative_checks()
    print("Regression framework tests passed.")
