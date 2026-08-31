import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthenticatedUser, RequestContext, authorize_tool  # noqa: E402
from core.structured_outputs import (  # noqa: E402
    FilterOutput,
    IntentOutput,
    RoutingOutput,
    ToolArgumentsOutput,
    build_filter_output,
    build_intent_output,
    build_policy_decision_output,
    build_routing_output,
    build_tool_arguments_output,
    json_schema_for,
    validate_structured_output,
)


def _context():
    return RequestContext(
        session_id="structured-test",
        user=AuthenticatedUser(
            user_id="11111111-1111-1111-1111-111111111111",
            email="customer@example.local",
            name="Customer",
            role="customer",
        ),
    )


def test_structured_intent_output_validates_with_pydantic():
    output = build_intent_output("Find black waterproof shoes under Rp 500,000")
    result = validate_structured_output(output.model_dump(), IntentOutput)

    assert result.valid is True
    assert result.data.intent == "PRODUCT_SEARCH"


def test_structured_filter_output_validates_hard_and_soft_constraints():
    output = build_filter_output("Find comfortable black waterproof shoes size 42 under Rp 500,000")
    result = validate_structured_output(output.model_dump(), FilterOutput)

    assert result.valid is True
    assert result.data.catalog_category == "Shoes"
    assert result.data.size == 42
    assert result.data.max_price == 500000


def test_structured_routing_and_tool_arguments_validate():
    context = _context()
    routing = build_routing_output("Please cancel order ORD002", context)
    tool_output = build_tool_arguments_output(
        "cancel_customer_order",
        {"order_id": "ORD002"},
        set(routing.exposed_tools),
        context,
    )

    assert validate_structured_output(routing.model_dump(), RoutingOutput).valid is True
    assert validate_structured_output(tool_output.model_dump(), ToolArgumentsOutput).valid is True
    assert tool_output.validation_pass is True


def test_policy_decision_output_validates_authorization_result():
    context = _context()
    authorization = authorize_tool("check_order_status", context)
    output = build_policy_decision_output(authorization, context, required_role="customer")

    assert output.allowed is True
    assert validate_structured_output(output.model_dump(), type(output)).valid is True


def test_controlled_retry_repairs_json_wrapped_in_text():
    payload = 'Here is the JSON:\n{"intent":"UNKNOWN","confidence":0.5,"language":"English","requires_tools":false,"security_flags":[]}'
    result = validate_structured_output(payload, IntentOutput, max_retries=1)

    assert result.valid is True
    assert result.repaired is True
    assert result.attempts == 2


def test_json_schema_generation():
    schema = json_schema_for(IntentOutput)

    assert schema["type"] == "object"
    assert "intent" in schema["properties"]


if __name__ == "__main__":
    test_structured_intent_output_validates_with_pydantic()
    test_structured_filter_output_validates_hard_and_soft_constraints()
    test_structured_routing_and_tool_arguments_validate()
    test_policy_decision_output_validates_authorization_result()
    test_controlled_retry_repairs_json_wrapped_in_text()
    test_json_schema_generation()
    print("Structured output tests passed.")
