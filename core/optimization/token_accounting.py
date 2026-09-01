import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TaskBudget:
    task: str
    input_limit: int
    output_limit: int
    conversation_turns: int
    retrieval_limit: int = 0


TASK_BUDGETS = {
    "intent": TaskBudget("intent", input_limit=500, output_limit=128, conversation_turns=0),
    "extraction": TaskBudget("extraction", input_limit=800, output_limit=256, conversation_turns=0),
    "product_search": TaskBudget("product_search", input_limit=1500, output_limit=500, conversation_turns=4),
    "orders": TaskBudget("orders", input_limit=1500, output_limit=500, conversation_turns=4),
    "cart": TaskBudget("cart", input_limit=1500, output_limit=500, conversation_turns=4),
    "escalation": TaskBudget("escalation", input_limit=1500, output_limit=400, conversation_turns=4),
    "simple_rag": TaskBudget("simple_rag", input_limit=3000, output_limit=700, conversation_turns=4, retrieval_limit=1800),
    "complex_rag": TaskBudget("complex_rag", input_limit=6000, output_limit=1200, conversation_turns=6, retrieval_limit=4200),
    "agentic_workflow": TaskBudget("agentic_workflow", input_limit=8000, output_limit=1200, conversation_turns=8, retrieval_limit=4500),
}


@dataclass(frozen=True)
class TokenBreakdown:
    task: str
    system_prompt_tokens: int
    user_tokens: int
    conversation_tokens: int
    retrieval_tokens: int
    tool_schema_tokens: int
    output_tokens: int
    total_input_tokens: int
    input_budget: int
    output_limit: int
    context_utilization_ratio: float
    within_budget: bool
    provider_prompt_cache_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def task_budget(task: str | None) -> TaskBudget:
    return TASK_BUDGETS.get(task or "", TASK_BUDGETS["agentic_workflow"])


def estimate_tokens(value: Any) -> int:
    """Deterministic provider-neutral estimate used for component accounting."""
    if value is None:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if not value:
        return 0
    pieces = re.findall(r"[\w]+|[^\w\s]", value, flags=re.UNICODE)
    lexical_estimate = len(pieces)
    character_floor = math.ceil(len(value.encode("utf-8")) / 4)
    return max(lexical_estimate, character_floor)


def account_llm_context(
    *,
    task: str,
    system_prompt: str = "",
    user_input: str = "",
    conversation: Any = "",
    retrieval_context: str = "",
    tools: list[Any] | None = None,
    output_tokens: int = 0,
    provider_prompt_cache_eligible: bool = False,
) -> TokenBreakdown:
    budget = task_budget(task)
    component_tokens = {
        "system_prompt_tokens": estimate_tokens(system_prompt),
        "user_tokens": estimate_tokens(user_input),
        "conversation_tokens": estimate_tokens(conversation),
        "retrieval_tokens": estimate_tokens(retrieval_context),
        "tool_schema_tokens": estimate_tokens([_tool_schema(tool) for tool in (tools or [])]),
    }
    total_input = sum(component_tokens.values())
    return TokenBreakdown(
        task=budget.task,
        output_tokens=max(0, int(output_tokens or 0)),
        total_input_tokens=total_input,
        input_budget=budget.input_limit,
        output_limit=budget.output_limit,
        context_utilization_ratio=round(total_input / budget.input_limit, 6),
        within_budget=total_input <= budget.input_limit,
        provider_prompt_cache_eligible=provider_prompt_cache_eligible,
        **component_tokens,
    )


def cost_per_correct_answer(total_cost_usd: float | None, correct_answers: int) -> float | None:
    if total_cost_usd is None or correct_answers <= 0:
        return None
    return round(float(total_cost_usd) / correct_answers, 10)


def _tool_schema(tool: Any) -> dict[str, Any]:
    schema = {}
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None and hasattr(args_schema, "model_json_schema"):
        schema = args_schema.model_json_schema()
    return {
        "name": getattr(tool, "name", getattr(tool, "__name__", str(tool))),
        "description": getattr(tool, "description", ""),
        "parameters": schema,
    }
