from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.optimization import summarize_token_trace  # noqa: E402


def test_token_trace_summary_aggregates_llm_calls():
    trace = {
        "request_id": "request-1",
        "workflow": "rag_policy",
        "request_latency_ms": 250,
        "lifecycle": [
            {
                "stage": "llm",
                "name": "llm.generate",
                "latency_ms": 100,
                "attributes": {
                    "provider": "openrouter",
                    "model": "openrouter/free",
                    "latency_ms": 95,
                    "cost_usd": 0,
                    "token_breakdown": {
                        "task": "simple_rag",
                        "system_prompt_tokens": 100,
                        "user_tokens": 10,
                        "conversation_tokens": 20,
                        "retrieval_tokens": 200,
                        "tool_schema_tokens": 50,
                        "output_tokens": 40,
                        "total_input_tokens": 380,
                        "input_budget": 3000,
                        "context_utilization_ratio": 0.126667,
                        "within_budget": True,
                    },
                },
            }
        ],
    }
    summary = summarize_token_trace(trace)
    assert summary["llm_calls"] == 1
    assert summary["input_tokens"] == 380
    assert summary["output_tokens"] == 40
    assert summary["total_tokens"] == 420
    assert summary["retrieval_tokens"] == 200
    assert summary["cost_usd"] == 0


def test_deterministic_request_reports_zero_llm_calls():
    summary = summarize_token_trace({"workflow": "product_search", "request_latency_ms": 12, "lifecycle": []})
    assert summary["llm_calls"] == 0
    assert summary["total_tokens"] == 0
    assert summary["request_latency_ms"] == 12


if __name__ == "__main__":
    test_token_trace_summary_aggregates_llm_calls()
    test_deterministic_request_reports_zero_llm_calls()
    print("Token usage UI tests passed.")
