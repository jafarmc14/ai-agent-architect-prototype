from .registry import PromptRegistry, prompt_registry


_active_registry: PromptRegistry = prompt_registry
_tenant_registries: dict[str, PromptRegistry] = {}


def get_prompt_version(prompt_id: str = "system"):
    from core.auth import get_request_context
    tenant = get_request_context().tenant_id
    registry = _active_registry if tenant == "default" else _tenant_registries.get(tenant, prompt_registry)
    return registry.active(prompt_id)


def get_system_prompt() -> str:
    return get_prompt_version("system").content


def get_system_prompt_metadata() -> dict:
    return get_prompt_version("system").metadata()


TASK_PROMPT_MODULES = {
    "product_search": "product",
    "product": "product",
    "simple_rag": "rag",
    "complex_rag": "rag",
    "rag_policy": "rag",
    "orders": "orders",
    "order_status": "orders",
    "transaction": "orders",
    "cart": "cart",
    "escalation": "escalation",
    "human_escalation": "escalation",
}


def get_task_prompt(task: str) -> str:
    base = get_prompt_version("base")
    module_id = TASK_PROMPT_MODULES.get(task)
    content = base.content if not module_id else f"{base.content}\n\n{get_prompt_version(module_id).content}"
    from core.auth import get_request_context
    if get_request_context().tenant_id != "default":
        from core.companies import company_instruction
        content += "\n\n" + company_instruction()
    return content


def get_task_prompt_metadata(task: str) -> dict:
    base = get_prompt_version("base")
    module_id = TASK_PROMPT_MODULES.get(task)
    modules = [base]
    if module_id:
        modules.append(get_prompt_version(module_id))
    return {
        "prompt_id": "+".join(prompt.prompt_id for prompt in modules),
        "version": "+".join(prompt.version for prompt in modules),
        "prompt_key": "+".join(prompt.key for prompt in modules),
        "created_at": max(prompt.created_at for prompt in modules),
        "status": "active",
        "evaluation_score": None,
        "modules": [prompt.metadata() for prompt in modules],
    }


def rollback_prompt_version(prompt_id: str, target_version: str) -> dict:
    global _active_registry
    from core.auth import get_request_context
    tenant = get_request_context().tenant_id
    if tenant == "default":
        _active_registry = _active_registry.rollback(prompt_id, target_version)
    else:
        _tenant_registries[tenant] = _tenant_registries.get(tenant, prompt_registry).rollback(prompt_id, target_version)
    return get_prompt_version(prompt_id).metadata()


SYSTEM_PROMPT_VERSION = get_prompt_version("system")
SYSTEM_PROMPT = get_system_prompt()
SYSTEM_PROMPT_METADATA = get_system_prompt_metadata()
