import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "datasets" / "conversation_state.jsonl"
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import RequestContext, request_context  # noqa: E402
from core.privacy import redact_for_logs  # noqa: E402
from core.services.conversation_service import ConversationService  # noqa: E402


class InMemoryConversationRepository:
    def __init__(self):
        self.conversations = {}
        self.messages = {}

    def get_or_create_conversation(self, *, session_id, user_id=None, tenant_id="default", channel="evaluation"):
        conversation_id = f"{tenant_id}:{user_id or session_id}"
        self.conversations.setdefault(
            conversation_id,
            {
                "id": conversation_id,
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "channel": channel,
                "structured_state": {},
            },
        )
        return dict(self.conversations[conversation_id])

    def append_message(
        self,
        *,
        conversation_id,
        role,
        content,
        tenant_id="default",
        metadata=None,
        tool_name="",
        tool_arguments=None,
        tool_output=None,
    ):
        self.messages.setdefault(conversation_id, []).append(
            {
                "role": role,
                "content": content,
                "tenant_id": tenant_id,
                "metadata": metadata or {},
                "tool_name": tool_name,
                "tool_arguments": tool_arguments or {},
                "tool_output": tool_output or {},
            }
        )

    def recent_messages(self, *, conversation_id, limit=6):
        return list(self.messages.get(conversation_id, []))[-limit:]

    def get_structured_state(self, *, conversation_id):
        return dict(self.conversations.get(conversation_id, {}).get("structured_state", {}))

    def update_structured_state(self, *, conversation_id, structured_state):
        self.conversations.setdefault(conversation_id, {})["structured_state"] = structured_state

    def reset_memory(self):
        self.conversations.clear()
        self.messages.clear()


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            case["line_number"] = line_number
            cases.append(case)
    return cases


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    repository = InMemoryConversationRepository()
    service = ConversationService(repository=repository)
    session_id = f"multiturn-{case['id']}"
    states = []
    start = time.perf_counter()

    with request_context(RequestContext(session_id=session_id, tenant_id="eval")):
        for turn in case.get("turns", []):
            state = service.update_structured_state(turn)
            states.append(redact_for_logs(state))

    final_state = states[-1] if states else {}
    expected_state = case.get("expected_state", {})
    expected_filters = case.get("expected_product_filters", {})
    actual_filters = final_state.get("last_product_filters", {})

    context_mismatches = _state_mismatches(final_state, expected_state)
    constraint_mismatches = _state_mismatches(actual_filters, expected_filters)
    consistency_mismatches = _consistency_mismatches(states)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "id": case["id"],
        "line_number": case["line_number"],
        "turns": case.get("turns", []),
        "expected_state": expected_state,
        "expected_product_filters": expected_filters,
        "final_state": final_state,
        "context_retention_pass": not context_mismatches,
        "constraint_retention_pass": not constraint_mismatches,
        "cross_turn_factual_consistency_pass": not consistency_mismatches,
        "context_mismatches": context_mismatches,
        "constraint_mismatches": constraint_mismatches,
        "consistency_mismatches": consistency_mismatches,
        "latency_ms": latency_ms,
    }


def _state_mismatches(actual: dict[str, Any], expected: dict[str, Any], prefix: str = "") -> list[str]:
    mismatches = []
    for key, expected_value in expected.items():
        label = f"{prefix}.{key}" if prefix else key
        actual_value = actual.get(key)
        if isinstance(expected_value, dict):
            mismatches.extend(_state_mismatches(actual_value or {}, expected_value, label))
        elif isinstance(expected_value, list):
            missing = [item for item in expected_value if item not in (actual_value or [])]
            if missing:
                mismatches.append(f"{label} missing {missing}, got {actual_value!r}")
        elif actual_value != expected_value:
            mismatches.append(f"{label} expected {expected_value!r}, got {actual_value!r}")
    return mismatches


def _consistency_mismatches(states: list[dict[str, Any]]) -> list[str]:
    mismatches = []
    last_order_ids = [state.get("last_order_id") for state in states if state.get("last_order_id")]
    if len(set(last_order_ids)) > 1:
        mismatches.append(f"last_order_id changed across turns: {last_order_ids}")

    previous_filters = {}
    for index, state in enumerate(states, start=1):
        filters = state.get("last_product_filters", {})
        for key in ("catalog_category", "color", "size", "waterproof", "max_price", "available"):
            if previous_filters.get(key) and not filters.get(key):
                mismatches.append(f"turn {index} dropped product filter {key}")
        if filters:
            previous_filters = filters
    return mismatches


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "total_cases": 0,
            "context_retention_rate": 0,
            "constraint_retention_rate": 0,
            "cross_turn_factual_consistency_rate": 0,
            "avg_latency_ms": 0,
        }
    return {
        "total_cases": total,
        "context_retention_passed": sum(1 for result in results if result["context_retention_pass"]),
        "context_retention_rate": round(sum(1 for result in results if result["context_retention_pass"]) / total, 4),
        "constraint_retention_passed": sum(1 for result in results if result["constraint_retention_pass"]),
        "constraint_retention_rate": round(sum(1 for result in results if result["constraint_retention_pass"]) / total, 4),
        "cross_turn_factual_consistency_passed": sum(
            1 for result in results if result["cross_turn_factual_consistency_pass"]
        ),
        "cross_turn_factual_consistency_rate": round(
            sum(1 for result in results if result["cross_turn_factual_consistency_pass"]) / total,
            4,
        ),
        "avg_latency_ms": round(sum(result["latency_ms"] for result in results) / total, 2),
        "max_latency_ms": max(result["latency_ms"] for result in results),
        "min_latency_ms": min(result["latency_ms"] for result in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-turn conversation state evaluation.")
    parser.add_argument("--dataset", default=str(DATASET_PATH), help="Path to JSONL multi-turn dataset.")
    args = parser.parse_args()

    cases = load_cases(Path(args.dataset))
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']}")
        results.append(evaluate_case(case))

    report = {
        "name": "multiturn_report_v1",
        "created_at": datetime.now().isoformat(),
        "dataset": str(Path(args.dataset)),
        "summary": summarize(results),
        "results": results,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = REPORT_DIR / "multiturn_report_latest.json"
    latest_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nMulti-turn evaluation complete.")
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
