from pathlib import Path
from types import SimpleNamespace
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import core.orchestration.runtime as runtime  # noqa: E402
from core.llm.base import LLMResponse  # noqa: E402
from core.orchestration.agent_loop_safety import (  # noqa: E402
    AgentLoopSafetyDecision,
    AgentLoopSafetyGuard,
)


def _call(name: str, value: int = 1) -> dict:
    return {"id": f"{name}-{value}", "name": name, "args": {"value": value}}


def _guard(**overrides) -> AgentLoopSafetyGuard:
    values = {
        "max_agent_steps": 10,
        "max_identical_tool_calls": 1,
        "max_low_progress_steps": 2,
        "max_planning_cycle_length": 3,
    }
    values.update(overrides)
    return AgentLoopSafetyGuard(**values)


def test_hard_agent_step_limit():
    guard = _guard(max_agent_steps=2)
    assert not guard.inspect_plan([_call("search", 1)], current_agent_steps=1).should_stop
    decision = guard.inspect_plan([_call("stock", 1)], current_agent_steps=2)
    assert decision.should_stop
    assert decision.reason == "hard_agent_step_limit"


def test_repeated_identical_tool_call_is_blocked_before_execution():
    guard = _guard()
    assert not guard.inspect_plan([_call("search", 1)], current_agent_steps=1).should_stop
    decision = guard.inspect_plan([_call("search", 1)], current_agent_steps=2)
    assert decision.should_stop
    assert decision.reason == "repeated_identical_tool_call"

    same_batch = _guard().inspect_plan(
        [_call("stock", 1), _call("stock", 1)],
        current_agent_steps=1,
    )
    assert same_batch.reason == "repeated_identical_tool_call"


def test_cyclic_planning_is_detected_with_changing_arguments():
    guard = _guard()
    plans = [
        [_call("search", 1)],
        [_call("stock", 1)],
        [_call("search", 2)],
        [_call("stock", 2)],
    ]
    decision = AgentLoopSafetyDecision()
    for step, plan in enumerate(plans, start=1):
        decision = guard.inspect_plan(plan, current_agent_steps=step)
    assert decision.should_stop
    assert decision.reason == "cyclic_planning"


def test_low_progress_uses_new_tool_evidence():
    guard = _guard()
    decisions = []
    for step, name in enumerate(("search", "stock", "policy"), start=1):
        assert not guard.inspect_plan([_call(name, step)], current_agent_steps=step).should_stop
        decisions.append(guard.record_tool_results(["same evidence"]))
    assert not decisions[0].should_stop
    assert not decisions[1].should_stop
    assert decisions[2].should_stop
    assert decisions[2].reason == "low_progress"


def test_safety_stop_escalates_once_without_another_agent_tool_step():
    class FakeSupportService:
        def __init__(self):
            self.calls = []

        def create_support_ticket(self, customer_message, **kwargs):
            self.calls.append({"customer_message": customer_message, **kwargs})
            return "Support ticket #TEST-LOOP created successfully."

    fake_support = FakeSupportService()
    original_support = runtime.support_service
    runtime.support_service = fake_support
    trace = {"tool_calls": []}
    guard = _guard()
    decision = AgentLoopSafetyDecision(True, "low_progress", "No new evidence.")
    try:
        response = runtime._escalate_agent_loop_safety("Please solve this", decision, guard, trace)
    finally:
        runtime.support_service = original_support

    assert len(fake_support.calls) == 1
    assert fake_support.calls[0]["escalation_type"] == "agent_loop_safety"
    assert "TEST-LOOP" in response
    assert trace["workflow"] == "agent_loop_safety_escalation"
    assert trace["tool_calls"][-1]["agent_loop_safety"] is True


def test_runtime_does_not_execute_a_repeated_tool_call():
    class FakeGateway:
        provider_name = "ollama"

        def __init__(self):
            self.calls = 0

        def generate_sync(self, *_args, **_kwargs):
            self.calls += 1
            tool_call = {"id": f"call-{self.calls}", "name": "search_products", "args": {"query": "shoes"}}
            return LLMResponse(raw=SimpleNamespace(content="", tool_calls=[tool_call]))

    class FakeTool:
        name = "search_products"

        def __init__(self):
            self.calls = 0

        def invoke(self, _args):
            self.calls += 1
            return "same product evidence"

    class FakeSupportService:
        def __init__(self):
            self.calls = 0

        def create_support_ticket(self, *_args, **_kwargs):
            self.calls += 1
            return "Support ticket #TEST-RUNTIME created successfully."

    fake_gateway = FakeGateway()
    fake_tool = FakeTool()
    fake_support = FakeSupportService()
    replacements = {
        "llm_gateway": fake_gateway,
        "support_service": fake_support,
        "tool_names_for_user_input": lambda *_args: {"search_products"},
        "_tools_by_names": lambda _names: [fake_tool],
        "tools_by_name": {"search_products": fake_tool},
        "validate_tool_call": lambda *_args: SimpleNamespace(allowed=True, reason="allowed"),
    }
    originals = {name: getattr(runtime, name) for name in replacements}
    for name, value in replacements.items():
        setattr(runtime, name, value)
    try:
        response = runtime._execute_agent("Find shoes")
    finally:
        for name, value in originals.items():
            setattr(runtime, name, value)

    assert fake_gateway.calls == 2
    assert fake_tool.calls == 1
    assert fake_support.calls == 1
    assert "TEST-RUNTIME" in response


if __name__ == "__main__":
    test_hard_agent_step_limit()
    test_repeated_identical_tool_call_is_blocked_before_execution()
    test_cyclic_planning_is_detected_with_changing_arguments()
    test_low_progress_uses_new_tool_evidence()
    test_safety_stop_escalates_once_without_another_agent_tool_step()
    test_runtime_does_not_execute_a_repeated_tool_call()
    print("Agent loop safety tests passed.")
