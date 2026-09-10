import asyncio
import json
import time

from configs.experimentation import experiment_settings
from core.optimization import estimate_tokens
from core.privacy import redact_for_logs
from core.repositories.production_monitoring_repository import ProductionMonitoringRepository
from core.services.response_experiments import READ_WORKFLOWS, candidate_gateway, proxy_quality, safe_prompt


async def run_job(job, settings, gateway_factory=candidate_gateway):
    payload = job["payload"]
    if settings.mode != "shadow" or job["tenant_id"] not in settings.tenants \
            or job["experiment_id"] != settings.experiment_id \
            or payload["provider"] != settings.provider or payload["model"] != settings.model:
        return "expired", {"reason": "experiment_disabled_or_changed"}
    if payload.get("workflow") not in READ_WORKFLOWS:
        return "error", {"reason": "workflow_not_allowed"}
    messages = safe_prompt(payload["messages"])
    if estimate_tokens(json.dumps(messages, default=str)) > settings.max_input_tokens:
        return "error", {"reason": "input_limit"}
    start = time.perf_counter()
    try:
        gateway = gateway_factory(settings.provider, settings.model)
        # No tools, no workflow execution, no writes. Async timeout cancels the provider call.
        # One adapter invocation, bounded by timeout; no orchestration fallback.
        response = await asyncio.wait_for(gateway.provider.generate(messages, tools=None,
            max_tokens=settings.max_output_tokens, timeout=settings.timeout), settings.timeout)
        if response.tool_calls:
            return "error", {"reason": "candidate_proposed_tools", "control": payload["control"]}
        return "completed", {
            "control": payload["control"],
            "candidate": {"latency_ms": round((time.perf_counter()-start)*1000),
                "model": response.model or settings.model, "model_version": response.model_version,
                "response": redact_for_logs(response.text), "usage": response.usage,
                "quality_proxy": proxy_quality(response.text, payload["evidence"], payload["workflow"]),
                **gateway._cost_attributes(response.usage or {}, gateway.provider)},
        }
    except Exception as exc:
        return "error", {"reason": type(exc).__name__, "latency_ms": round((time.perf_counter()-start)*1000),
                         "control": payload.get("control"), "cost_usd": None}


def drain(tenant_id, limit=5):
    settings = experiment_settings()
    if settings.mode != "shadow" or tenant_id not in settings.tenants:
        raise ValueError("Shadow worker requires an active shadow experiment and allowed tenant")
    repo = ProductionMonitoringRepository()
    outcomes = []
    for _ in range(min(limit, settings.daily_jobs)):
        job = repo.claim_shadow(tenant_id, settings.experiment_id)
        if not job:
            break
        state, result = asyncio.run(run_job(job, settings))
        repo.finish_shadow(job["id"], state, result)
        outcomes.append({"id": str(job["id"]), "status": state})
    return outcomes
