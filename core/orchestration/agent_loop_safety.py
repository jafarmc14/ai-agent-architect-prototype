import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentLoopSafetyDecision:
    should_stop: bool = False
    reason: str = ""
    detail: str = ""


@dataclass
class AgentLoopSafetyGuard:
    max_agent_steps: int
    max_identical_tool_calls: int = 1
    max_low_progress_steps: int = 2
    max_planning_cycle_length: int = 3
    planning_steps: int = 0
    low_progress_steps: int = 0
    tool_call_counts: Counter = field(default_factory=Counter)
    plan_history: list[tuple[str, ...]] = field(default_factory=list)
    evidence_hashes: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if min(
            self.max_agent_steps,
            self.max_identical_tool_calls,
            self.max_low_progress_steps,
            self.max_planning_cycle_length,
        ) <= 0:
            raise ValueError("Agent loop safety limits must be positive.")

    def inspect_plan(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        current_agent_steps: int,
    ) -> AgentLoopSafetyDecision:
        self.planning_steps += 1
        fingerprints = [_tool_fingerprint(call) for call in tool_calls]
        proposed_counts: Counter = Counter()
        for fingerprint in fingerprints:
            if (
                self.tool_call_counts[fingerprint] + proposed_counts[fingerprint]
                >= self.max_identical_tool_calls
            ):
                return self._stop(
                    "repeated_identical_tool_call",
                    "The same tool and validated arguments were proposed again.",
                )
            proposed_counts[fingerprint] += 1

        self.tool_call_counts.update(proposed_counts)
        self.plan_history.append(tuple(_tool_name(call) for call in tool_calls))
        if self._has_planning_cycle():
            return self._stop(
                "cyclic_planning",
                "The sequence of planned tool names entered a repeating cycle.",
            )
        if current_agent_steps >= self.max_agent_steps:
            return self._stop(
                "hard_agent_step_limit",
                f"Agent produced another tool plan at hard step limit {self.max_agent_steps}.",
            )
        return AgentLoopSafetyDecision()

    def record_tool_results(self, outputs: list[str]) -> AgentLoopSafetyDecision:
        result_hashes = {_evidence_hash(output) for output in outputs}
        has_new_evidence = bool(result_hashes - self.evidence_hashes)
        self.evidence_hashes.update(result_hashes)
        if has_new_evidence:
            self.low_progress_steps = 0
        else:
            self.low_progress_steps += 1

        if self.low_progress_steps >= self.max_low_progress_steps:
            return self._stop(
                "low_progress",
                f"Tool results added no new evidence for {self.low_progress_steps} consecutive steps.",
            )
        return AgentLoopSafetyDecision()

    def snapshot(self) -> dict[str, Any]:
        return {
            "planning_steps": self.planning_steps,
            "low_progress_steps": self.low_progress_steps,
            "unique_tool_calls": len(self.tool_call_counts),
            "unique_evidence": len(self.evidence_hashes),
            "plan_history": [list(plan) for plan in self.plan_history],
        }

    def _has_planning_cycle(self) -> bool:
        history = self.plan_history
        max_cycle = min(self.max_planning_cycle_length, len(history) // 2)
        for cycle_length in range(1, max_cycle + 1):
            repetitions = 3 if cycle_length == 1 else 2
            required = cycle_length * repetitions
            if len(history) < required:
                continue
            tail = history[-cycle_length:]
            if all(
                history[-offset * cycle_length:-(offset - 1) * cycle_length] == tail
                for offset in range(2, repetitions + 1)
            ):
                return True
        return False

    @staticmethod
    def _stop(reason: str, detail: str) -> AgentLoopSafetyDecision:
        return AgentLoopSafetyDecision(should_stop=True, reason=reason, detail=detail)


def _tool_name(tool_call: dict[str, Any]) -> str:
    return str(tool_call.get("name", "")).strip().lower()


def _tool_fingerprint(tool_call: dict[str, Any]) -> str:
    payload = {
        "name": _tool_name(tool_call),
        "args": tool_call.get("args") or {},
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _evidence_hash(output: str) -> str:
    normalized = re.sub(r"\s+", " ", str(output)).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
