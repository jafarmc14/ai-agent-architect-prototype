import hashlib
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1] / "companies"
KNOWN_TOOLS = {"check_stock", "check_order_status", "search_products", "cancel_customer_order", "update_shipping_address",
               "add_product_to_cart", "view_shopping_cart", "clear_shopping_cart", "search_knowledge_base", "escalate_to_human"}


class CompanyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Literal["demo", "company_a", "company_b"]
    version: str = Field(min_length=1)
    currency: Literal["IDR", "USD", "EUR"]
    language: Literal["match_user", "English", "Indonesian"]
    tools: list[str]
    policy_categories: list[str]
    routing: dict[str, dict[str, str]]
    require_high_risk_approval: Literal[True] = True
    autonomy_enabled: bool = False
    max_plan_steps: int = Field(default=3, ge=1, le=5)
    max_concurrency: int = Field(default=4, ge=1, le=16)
    max_input_tokens: int = Field(default=8000, ge=100, le=8000)
    max_output_tokens: int = Field(default=1200, ge=50, le=2000)


def company_config(tenant_id=None):
    if tenant_id is None:
        from core.auth import get_request_context
        tenant_id = get_request_context().tenant_id
    tenants = json.loads((ROOT / "tenants.json").read_text(encoding="utf-8"))
    name = tenants.get(tenant_id)
    if name not in {"demo", "company_a", "company_b"}:
        raise PermissionError("Tenant is not configured.")
    config = CompanyConfig.model_validate_json((ROOT / name / "config.json").read_text(encoding="utf-8"))
    if config.id != name or not set(config.tools) <= KNOWN_TOOLS:
        raise ValueError("Invalid company tools or identity")
    if not set(config.routing) <= {"cheap", "standard", "premium"}:
        raise ValueError("Company routing keys must be cheap, standard or premium")
    for target in config.routing.values():
        if set(target) != {"provider", "model"} or target["provider"] not in {"ollama", "openrouter", "deepseek", "kimi"} or not target["model"]:
            raise ValueError("Invalid company routing target")
    return config


def company_key():
    from core.auth import get_request_context
    config = company_config()
    digest = hashlib.sha256(config.model_dump_json().encode()).hexdigest()
    return f"{get_request_context().tenant_id}:{config.id}:{config.version}:{digest}"


def company_instruction():
    config = company_config()
    return f"Company: {config.id}. Currency: {config.currency}. Response language: {config.language}. Never convert or invent prices."


def money(amount):
    currency = company_config().currency
    return f"Rp{amount:,.0f}" if currency == "IDR" else f"{currency} {amount:,.2f}"


_slots = {}
_slots_lock = threading.Lock()


@contextmanager
def company_slot():
    from core.auth import get_request_context
    profile = company_config()
    key = (get_request_context().tenant_id, profile.max_concurrency)
    with _slots_lock:
        semaphore = _slots.setdefault(key, threading.BoundedSemaphore(profile.max_concurrency))
    if not semaphore.acquire(blocking=False):
        raise RuntimeError("Company request capacity reached. Please retry later.")
    try:
        yield
    finally:
        semaphore.release()
