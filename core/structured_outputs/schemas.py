from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IntentName = Literal[
    "PRODUCT_SEARCH",
    "PRODUCT_INFO",
    "PRODUCT_COMPARE",
    "ORDER_STATUS",
    "RETURN_POLICY",
    "CART",
    "TRANSACTION",
    "COMPLAINT",
    "ESCALATION",
    "GENERAL_FAQ",
    "UNKNOWN",
]

WorkflowName = Literal[
    "rag_policy",
    "order_status",
    "product_search",
    "agent_loop",
    "security_refusal",
]

ToolName = Literal[
    "check_stock",
    "check_order_status",
    "search_products",
    "cancel_customer_order",
    "update_shipping_address",
    "add_product_to_cart",
    "view_shopping_cart",
    "clear_shopping_cart",
    "search_knowledge_base",
    "escalate_to_human",
]

PolicyDecision = Literal["allow", "deny", "abstain", "escalate"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class IntentOutput(StrictModel):
    intent: IntentName
    confidence: float = Field(ge=0, le=1)
    language: str = Field(min_length=1, max_length=40)
    requires_tools: bool
    security_flags: list[str] = Field(default_factory=list)


class FilterOutput(StrictModel):
    query: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=80)
    catalog_category: str = Field(default="", max_length=80)
    size: int | None = Field(default=None, ge=1, le=200)
    color: str = Field(default="", max_length=40)
    waterproof: bool | None = None
    sku: str = Field(default="", max_length=80)
    available: bool | None = None
    min_stock: int = Field(default=0, ge=0)
    min_price: float = Field(default=0, ge=0)
    max_price: float = Field(default=0, ge=0)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    soft_constraints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_price_range(self):
        if self.min_price and self.max_price and self.min_price > self.max_price:
            raise ValueError("min_price cannot be greater than max_price")
        return self


class RoutingOutput(StrictModel):
    intent: IntentName
    workflow: WorkflowName
    use_agent_loop: bool
    reason: str = Field(min_length=1, max_length=500)
    exposed_tools: list[ToolName] = Field(default_factory=list)
    security_flags: list[str] = Field(default_factory=list)


class ToolArgumentsOutput(StrictModel):
    tool_name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    validation_pass: bool
    validation_reason: str = Field(min_length=1, max_length=500)

    @field_validator("arguments")
    @classmethod
    def arguments_must_be_json_object(cls, value):
        if not isinstance(value, dict):
            raise ValueError("arguments must be an object")
        return value


class PolicyDecisionOutput(StrictModel):
    decision: PolicyDecision
    allowed: bool
    reason: str = Field(min_length=1, max_length=500)
    required_role: str = Field(default="", max_length=80)
    access_level: str = Field(default="public", max_length=80)
    security_flags: list[str] = Field(default_factory=list)
