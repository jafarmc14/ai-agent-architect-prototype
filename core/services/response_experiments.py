"""Experiments only synthesize answers from already-authorized read evidence."""
import hashlib
import json
import logging
import time
from dataclasses import replace

from configs import get_settings
from configs.experimentation import experiment_settings
from core.auth import get_request_context
from core.hallucination import audit_response_claims
from core.optimization import estimate_tokens
from core.privacy import redact_for_llm, redact_for_logs
from core.repositories.production_monitoring_repository import ProductionMonitoringRepository

READ_WORKFLOWS = {"search_knowledge_base"}


def bucket(experiment_id, tenant_id, user_id):
    digest = hashlib.sha256(json.dumps([experiment_id, tenant_id, user_id]).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 * 100


def eligible(workflow):
    settings = experiment_settings()
    context = get_request_context()
    return settings.mode != "off" and get_settings().database_provider == "postgres" and workflow in READ_WORKFLOWS \
        and context.is_authenticated and context.tenant_id in settings.tenants


def candidate_gateway(provider, model):
    from core.llm.gateway import LLMGateway
    from core.llm.model_routing import ModelRouter

    gateway = LLMGateway()
    gateway.configure(provider, model)
    gateway.model_router = ModelRouter(replace(get_settings(), model_routing_enabled=False))
    return gateway


def safe_prompt(messages):
    result = []
    for message in messages:
        role = message.get("role") if isinstance(message, dict) else {"human": "user", "system": "system", "ai": "assistant"}.get(getattr(message, "type", ""))
        if role not in {"user", "system", "assistant"}:
            raise ValueError("Experiment prompts cannot contain tool messages")
        content = message.get("content", "") if isinstance(message, dict) else message.content
        result.append({"role": role, "content": redact_for_llm(content)})
    return result


def proxy_quality(text, evidence, workflow):
    audit = audit_response_claims(text, tool_outputs=[evidence],
                                  rag_evidence=evidence if workflow == "search_knowledge_base" else "")
    return {"claim_support_proxy": 1 - audit.unsupported_claim_rate if audit.claims else None,
            "unsupported_critical_claims": audit.unsupported_critical_claim_count,
            "abstain_recommended": audit.should_abstain}


def generate_answer(gateway, messages, *, task, token_context, workflow, evidence, trace):
    if not eligible(workflow):
        return gateway.generate_sync(messages, task=task, token_context=token_context)
    settings, context = experiment_settings(), get_request_context()
    assigned = bucket(settings.experiment_id, context.tenant_id, context.user_id) < settings.percentage
    arm = "candidate" if settings.mode == "ab" and assigned else "control"
    # Redact for every experiment, even when the current provider is local.
    safe_messages = safe_prompt(messages)
    safe_context = redact_for_llm(token_context)
    safe_evidence = redact_for_llm(evidence)
    experiment = {"id": settings.experiment_id, "mode": settings.mode, "arm": arm, "percentage": settings.percentage,
                  "candidate_provider": settings.provider, "candidate_model": settings.model,
                  "control_provider": gateway.provider_name, "control_model": gateway.model,
                  "contaminated": False}
    if trace is not None:
        trace["experiment"] = experiment
    start = time.perf_counter()
    try:
        selected = candidate_gateway(settings.provider, settings.model) if arm == "candidate" else gateway
        response = selected.generate_sync(safe_messages if arm == "candidate" else messages,
                                          task=task, token_context=safe_context if arm == "candidate" else token_context)
    except Exception:
        experiment["contaminated"] = True
        raise
    elapsed = round((time.perf_counter() - start) * 1000)
    actual = response.model or selected.model
    experiment["actual_model"] = actual
    experiment["raw_quality_proxy"] = proxy_quality(response.text, safe_evidence, workflow)
    experiment["prompt"] = (token_context.get("prompt_metadata") or {}).get("prompt_key")
    if actual != selected.model or get_settings().provider_fallback_enabled or get_settings().model_routing_enabled:
        experiment["contaminated"] = True
    if response.tool_calls:
        experiment["contaminated"] = True
        raise ValueError("Read-only answer experiment returned tool calls")
    if settings.mode == "shadow" and assigned:
        tokens = estimate_tokens(json.dumps(safe_messages, default=str))
        if tokens <= settings.max_input_tokens:
            try:
                payload = {"messages": safe_messages, "evidence": safe_evidence, "workflow": workflow, "task": task,
                           "provider": settings.provider, "model": settings.model,
                           "control": {"latency_ms": elapsed, "model": actual,
                                       "quality_proxy": experiment["raw_quality_proxy"],
                                       **gateway._cost_attributes(response.usage or {}, gateway.provider)}}
                queued = ProductionMonitoringRepository().enqueue(context.request_id, context.tenant_id,
                    settings.experiment_id, payload, settings.daily_jobs)
                experiment["shadow_status"] = "queued" if queued else "daily_limit"
            except Exception:
                experiment["shadow_status"] = "queue_error"
                logging.getLogger(__name__).warning("Shadow enqueue failed")
        else:
            experiment["shadow_status"] = "input_limit"
    return response
