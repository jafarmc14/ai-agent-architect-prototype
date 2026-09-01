from pathlib import Path
import sys
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.embeddings import OpenAICompatibleEmbeddingProvider
from core.optimization import TTLCache, account_llm_context, compress_context, embedding_cache, estimate_tokens
from core.prompts import get_task_prompt, get_task_prompt_metadata
from evaluation.run_token_regression import compare


def test_component_accounting_and_budget():
    result = account_llm_context(
        task="product_search",
        system_prompt="system",
        user_input="find shoes",
        conversation="previous turn",
        retrieval_context="database row",
        tools=[],
    )
    assert result.total_input_tokens == sum((
        result.system_prompt_tokens,
        result.user_tokens,
        result.conversation_tokens,
        result.retrieval_tokens,
        result.tool_schema_tokens,
    ))
    assert result.input_budget == 1500
    assert result.within_budget


def test_modular_prompt_and_compression():
    prompt = get_task_prompt("simple_rag")
    metadata = get_task_prompt_metadata("simple_rag")
    assert "POLICY/RAG TASK" in prompt
    assert metadata["prompt_id"] == "base+rag"
    compressed = compress_context("Return policy applies.\nReturn policy applies.\nUnrelated long content " * 50, 30, "return policy")
    assert estimate_tokens(compressed) <= 30


def test_cache_key_is_scope_aware():
    cache = TTLCache()
    cache.set({"tenant": "a", "query": "return"}, "tenant-a")
    assert cache.get({"tenant": "a", "query": "return"}) == "tenant-a"
    assert cache.get({"tenant": "b", "query": "return"}) is None


def test_embedding_cache_avoids_duplicate_provider_calls():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":[{"embedding":[0.1,0.2]}]}'

    embedding_cache.clear()
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        api_base="http://embedding.test/v1",
        model="test-model",
    )
    with patch("urllib.request.urlopen", return_value=Response()) as request:
        assert provider.embed_text("same query") == [0.1, 0.2]
        assert provider.embed_text("same query") == [0.1, 0.2]
    assert request.call_count == 1


def test_regression_gate_blocks_unjustified_twenty_percent_increase():
    baseline = {"summary": {"quality_score": 1.0}, "tasks": {"intent": {"total_input_tokens": 100}}}
    candidate = {
        "summary": {"quality_score": 1.0},
        "tasks": {"intent": {"total_input_tokens": 121, "within_budget": True}},
    }
    assert compare(baseline, candidate)["status"] == "FAIL"


if __name__ == "__main__":
    test_component_accounting_and_budget()
    test_modular_prompt_and_compression()
    test_cache_key_is_scope_aware()
    test_embedding_cache_avoids_duplicate_provider_calls()
    test_regression_gate_blocks_unjustified_twenty_percent_increase()
    print("Token optimization tests passed.")
