from .registry import PromptRegistry, prompt_registry


_active_registry: PromptRegistry = prompt_registry


def get_prompt_version(prompt_id: str = "system"):
    return _active_registry.active(prompt_id)


def get_system_prompt() -> str:
    return get_prompt_version("system").content


def get_system_prompt_metadata() -> dict:
    return get_prompt_version("system").metadata()


def rollback_prompt_version(prompt_id: str, target_version: str) -> dict:
    global _active_registry
    _active_registry = _active_registry.rollback(prompt_id, target_version)
    return get_prompt_version(prompt_id).metadata()


SYSTEM_PROMPT_VERSION = get_prompt_version("system")
SYSTEM_PROMPT = get_system_prompt()
SYSTEM_PROMPT_METADATA = get_system_prompt_metadata()
