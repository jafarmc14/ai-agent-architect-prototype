from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import RequestContext, request_context  # noqa: E402
from core.orchestration import runtime  # noqa: E402


def test_out_of_scope_question_is_deterministic_and_grounded():
    calls = []
    original_generate = runtime.llm_gateway.generate_sync
    runtime.llm_gateway.generate_sync = lambda *_args, **_kwargs: calls.append(True)
    trace = {}
    try:
        with request_context(RequestContext(session_id="scope-test")):
            response = runtime._execute_routed_workflow(
                "What is the recipe for Korean chicken?",
                trace=trace,
            )
    finally:
        runtime.llm_gateway.generate_sync = original_generate

    assert "only help with store" in response
    assert "gochujang" not in response.lower()
    assert trace["intent"] == "UNKNOWN"
    assert trace["workflow"] == "out_of_scope"
    assert trace["deterministic_first"] is True
    assert calls == []


def test_out_of_scope_response_matches_indonesian_input():
    with request_context(RequestContext(session_id="scope-test-id")):
        response = runtime._execute_routed_workflow("Apa resep ayam Korea?", trace={})
    assert response.startswith("Saya hanya dapat membantu")


if __name__ == "__main__":
    test_out_of_scope_question_is_deterministic_and_grounded()
    test_out_of_scope_response_matches_indonesian_input()
    print("Scope control tests passed.")
