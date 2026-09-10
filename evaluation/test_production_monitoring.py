import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.services.production_metrics import capture_metrics, distribution_drift, monitoring_report, promotion_gate
from core.services.response_experiments import bucket, safe_prompt
from core.services.shadow_worker import run_job
from core.llm.base import LLMResponse, LLMToolCall


def row(user="u", arm="control", correct=True):
    return {"user_id": user, "metrics": {"intent": "PRODUCT_SEARCH", "language_heuristic": "en",
            "abstained": False, "escalated": False, "experiment": {"id": "test", "mode": "ab", "arm": arm}},
            "review": {"correct": correct, "critical_failure": False, "faithfulness": 1.0, "tool_accuracy": True},
            "tokens": 100, "latency_ms": 500, "cost_usd": .001, "negative_feedback": False}


def test_metrics_and_missing_data():
    metrics = capture_metrics("apakah sepatu saya tersedia", {"tool_calls": [{"validation_pass": True}]})
    assert metrics["language_heuristic"] == "id"
    assert metrics["claim_support_proxy"] is None
    report = monitoring_report([], [])
    assert report["status"] == "insufficient_data"
    assert report["current"]["faithfulness"] is None
    assert distribution_drift(["en"]*30, ["id"]*30) == 1
    previous = [row(str(i)) for i in range(30)]
    current = [dict(row(str(i)), tokens=130, latency_ms=700, cost_usd=.002) for i in range(30)]
    report = monitoring_report(previous, current)
    assert set(report["alerts"]) >= {"avg_tokens", "avg_latency_ms", "avg_cost_usd"}
    current[0]["review"] = None
    current[0]["cost_usd"] = None
    assert monitoring_report(previous, current)["current"]["unknown_cost_requests"] == 1


def test_assignment_and_prompt_redaction():
    assert bucket("exp", "tenant", "user") == bucket("exp", "tenant", "user")
    assert bucket("exp", "tenant", "user") != bucket("exp", "other", "user")
    percentage = sum(bucket("exp", "tenant", str(i)) < 10 for i in range(10000))/10000
    assert .08 < percentage < .12
    from langchain_core.messages import HumanMessage
    messages = safe_prompt([HumanMessage(content="Email me at private@example.com")])
    assert messages[0]["role"] == "user"
    assert "private@example.com" not in messages[0]["content"]
    try:
        safe_prompt([{"role": "tool", "content": "execute"}])
        raise AssertionError("Tool messages accepted")
    except ValueError:
        pass


def test_promotion_requires_evidence():
    assert not promotion_gate([], "test")["promotable"]
    rows = [row(f"c{i}", correct=i < 50) for i in range(200)] + [row(f"t{i}", "candidate") for i in range(200)]
    assert promotion_gate(rows, "test")["promotable"]
    rows[-1]["review"]["critical_failure"] = True
    assert not promotion_gate(rows, "test")["promotable"]
    shadow_rows = [row(f"c{i}", correct=i < 50) for i in range(200)] + [row(f"t{i}", "candidate") for i in range(200)]
    for sample in shadow_rows:
        sample["metrics"]["experiment"]["mode"] = "shadow"
    assert not promotion_gate(shadow_rows, "test")["promotable"]
    repeated = [row("one", "candidate") for _ in range(1000)]
    assert not promotion_gate(repeated, "test")["promotable"]
    rows[-1]["review"]["critical_failure"] = False
    rows[-1]["cost_usd"] = None
    assert not promotion_gate(rows, "test")["promotable"]


def test_shadow_is_isolated_and_bounded():
    calls = []
    class Provider:
        async def generate(self, messages, tools=None, **kwargs):
            calls.append((messages, tools, kwargs))
            return LLMResponse(text="Hello", usage={"input_tokens": 10, "output_tokens": 2})
    gateway = SimpleNamespace(provider=Provider(), _cost_attributes=lambda *a: {"cost_usd": None})
    settings = SimpleNamespace(mode="shadow", tenants=("store",), experiment_id="exp", provider="ollama", model="candidate",
                               max_input_tokens=3000, max_output_tokens=50, timeout=.02)
    job = {"tenant_id": "store", "experiment_id": "exp", "payload": {"provider": "ollama", "model": "candidate",
           "messages": [{"role": "user", "content": "Hello"}], "evidence": "", "workflow": "search_knowledge_base", "control": {"latency_ms": 3}}}
    status, result = asyncio.run(run_job(job, settings, lambda *a: gateway))
    assert status == "completed" and result["candidate"]["response"] == "Hello"
    assert calls[0][1] is None and calls[0][2]["max_tokens"] == 50
    settings.mode = "off"
    assert asyncio.run(run_job(job, settings, lambda *a: gateway))[0] == "expired"
    assert len(calls) == 1
    settings.mode = "shadow"
    async def malicious(*a, **kw):
        return LLMResponse(tool_calls=[LLMToolCall("id", "cancel_customer_order", {})])
    gateway.provider.generate = malicious
    assert asyncio.run(run_job(job, settings, lambda *a: gateway))[0] == "error"
    async def slow(*a, **kw):
        await asyncio.sleep(1)
    gateway.provider.generate = slow
    assert asyncio.run(run_job(job, settings, lambda *a: gateway))[1]["reason"] == "TimeoutError"


def test_experiment_does_not_change_global_gateway_or_run_tools():
    from core.services.response_experiments import generate_answer
    settings = SimpleNamespace(mode="ab", experiment_id="exp", provider="ollama", model="candidate", percentage=10)
    context = SimpleNamespace(tenant_id="store", user_id="u", request_id="r")
    calls = []
    class Gateway:
        provider_name = "ollama"
        model = "control"
        def generate_sync(self, messages, **kwargs):
            assert "tools" not in kwargs
            calls.append(self.model)
            return LLMResponse(text="Hello", model=self.model)
    control, candidate = Gateway(), Gateway()
    candidate.model = "candidate"
    with patch("core.services.response_experiments.eligible", return_value=True), \
         patch("core.services.response_experiments.experiment_settings", return_value=settings), \
         patch("core.services.response_experiments.get_request_context", return_value=context), \
         patch("core.services.response_experiments.get_settings", return_value=SimpleNamespace(provider_fallback_enabled=False, model_routing_enabled=False)), \
         patch("core.services.response_experiments.candidate_gateway", return_value=candidate), \
         patch("core.services.response_experiments.bucket", return_value=1):
        trace = {}
        response = generate_answer(control, [{"role": "user", "content": "Hi"}], task="simple_rag", token_context={},
                                   workflow="search_knowledge_base", evidence="", trace=trace)
        assert response.model == "candidate" and control.model == "control"
        assert calls == ["candidate"] and trace["experiment"]["arm"] == "candidate"


def test_monitoring_api_requires_review_role_and_tenant_scope():
    from fastapi.testclient import TestClient
    import api.main as main
    from uuid import uuid4

    claims = {"sub": "reviewer", "tenant_id": "store", "role": "customer"}
    request_id = str(uuid4())
    with patch.object(main, "_feedback_identity", return_value=claims), \
         patch.object(main, "ProductionMonitoringRepository") as repository:
        client = TestClient(main.create_app())
        assert client.get("/api/v1/monitoring/quality").status_code == 403
        assert client.post(f"/api/v1/monitoring/reviews/{request_id}", json={
            "correct": True, "faithfulness": 1.0, "critical_failure": False}).status_code == 403
        claims["role"] = "manager"
        repository.return_value.rows.return_value = ([], [])
        assert client.get("/api/v1/monitoring/quality?days=7").status_code == 200
        repository.return_value.rows.assert_called_with("store", 7)
        repository.return_value.review.return_value = False
        assert client.post(f"/api/v1/monitoring/reviews/{request_id}", json={
            "correct": True, "faithfulness": 1.0, "critical_failure": False}).status_code == 404
        assert client.post(f"/api/v1/monitoring/reviews/{request_id}", json={
            "correct": True, "faithfulness": 1.0, "critical_failure": False, "tenant_id": "other"}).status_code == 422
        assert client.get("/api/v1/monitoring/experiments/test?days=30").json()["promotable"] is False


if __name__ == "__main__":
    test_metrics_and_missing_data()
    test_assignment_and_prompt_redaction()
    test_promotion_requires_evidence()
    test_shadow_is_isolated_and_bounded()
    test_experiment_does_not_change_global_gateway_or_run_tools()
    test_monitoring_api_requires_review_role_and_tenant_scope()
    print("Production monitoring, drift, shadow and A/B tests passed.")
