"""Bounded proposed plans. Write tools can propose confirmation, never auto-confirm."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.auth import get_request_context
from core.companies import company_config
from core.security.prompt_injection import validate_tool_call

READ_TOOLS = {"check_stock", "check_order_status", "search_products", "view_shopping_cart", "search_knowledge_base"}
CONFIRMATION_TOOLS = {"add_product_to_cart", "clear_shopping_cart", "cancel_customer_order", "update_shipping_address"}


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    tool: str
    arguments: dict[str, Any]
    depends_on: list[str] = Field(default_factory=list, max_length=5)
    condition: Literal["always", "on_success", "on_failure"] = "always"


class ConditionalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[PlanStep] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def acyclic(self):
        seen = set()
        for step in self.steps:
            if step.id in seen or not set(step.depends_on) <= seen:
                raise ValueError("Plan must have unique IDs and depend only on preceding steps")
            if step.condition != "always" and not step.depends_on:
                raise ValueError("Conditional steps require dependencies")
            seen.add(step.id)
        return self


def execute_plan(plan, tools, before_tool, trace):
    profile = company_config()
    if not profile.autonomy_enabled:
        raise PermissionError("Advanced planning is disabled for this company")
    plan = ConditionalPlan.model_validate(plan)
    if len(plan.steps) > profile.max_plan_steps:
        raise ValueError("Company plan step budget exceeded")
    context = get_request_context()
    exposed = set(tools) & set(profile.tools) & (READ_TOOLS | CONFIRMATION_TOOLS)
    # Validate the entire proposal before executing its first tool.
    for step in plan.steps:
        check = validate_tool_call(step.tool, step.arguments, exposed, context)
        if not check.allowed:
            raise PermissionError(check.reason)
    results = {}
    for step in plan.steps:
        success = all(results[parent]["status"] == "success" for parent in step.depends_on)
        if (step.condition == "on_success" and not success) or (step.condition == "on_failure" and success):
            results[step.id] = {"status": "skipped"}
            continue
        before_tool(step.tool)
        from core.observability.service import observed_span
        from core.privacy import redact_for_logs
        try:
            with observed_span("tool", f"tool.{step.tool}"):
                output = tools[step.tool].invoke(step.arguments)
        except Exception:
            results[step.id] = {"status": "error", "output": "Tool execution failed."}
            continue
        checkpoint = step.tool in CONFIRMATION_TOOLS
        results[step.id] = {"status": "approval_required" if checkpoint else "success", "output": str(output)}
        trace.setdefault("tool_calls", []).append({"name": step.tool, "args": redact_for_logs(step.arguments),
                                                   "output": redact_for_logs(str(output)), "validation_pass": True})
        if checkpoint:
            break
    trace["plan_results"] = {key: {"status": value["status"]} for key, value in results.items()}
    return results
