import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable


@dataclass
class _CircuitState:
    state: str = "closed"
    consecutive_failures: int = 0
    opened_at: float | None = None
    half_open_probe_in_flight: bool = False


@dataclass(frozen=True)
class CircuitDecision:
    allowed: bool
    provider: str
    model: str
    state: str
    consecutive_failures: int
    retry_after_seconds: float
    reason: str

    def metadata(self) -> dict[str, Any]:
        return asdict(self)


class CircuitOpenError(RuntimeError):
    """All usable provider candidates currently have an open circuit."""


class ProviderCircuitBreaker:
    """Thread-safe process-local provider health state with half-open recovery probes."""

    def __init__(self, settings: Any, clock: Callable[[], float] | None = None):
        self.settings = settings
        self.clock = clock or time.monotonic
        self._states: dict[str, _CircuitState] = {}
        self._lock = threading.RLock()

    def before_request(self, provider: str, model: str) -> CircuitDecision:
        if not self.settings.circuit_breaker_enabled:
            return CircuitDecision(True, provider, model, "disabled", 0, 0.0, "circuit_breaker_disabled")

        with self._lock:
            state = self._states.setdefault(_key(provider, model), _CircuitState())
            now = self.clock()
            if state.state == "open":
                elapsed = now - float(state.opened_at or now)
                remaining = max(0.0, self.settings.circuit_breaker_cooldown_seconds - elapsed)
                if remaining > 0:
                    return self._decision(False, provider, model, state, remaining, "cooldown_active")
                state.state = "half_open"
                state.half_open_probe_in_flight = False

            if state.state == "half_open":
                if state.half_open_probe_in_flight:
                    return self._decision(False, provider, model, state, 0.0, "half_open_probe_in_flight")
                state.half_open_probe_in_flight = True
                return self._decision(True, provider, model, state, 0.0, "half_open_probe_allowed")

            return self._decision(True, provider, model, state, 0.0, "closed")

    def record_success(self, provider: str, model: str) -> CircuitDecision:
        if not self.settings.circuit_breaker_enabled:
            return CircuitDecision(True, provider, model, "disabled", 0, 0.0, "success_ignored_disabled")
        with self._lock:
            state = self._states.setdefault(_key(provider, model), _CircuitState())
            state.state = "closed"
            state.consecutive_failures = 0
            state.opened_at = None
            state.half_open_probe_in_flight = False
            return self._decision(True, provider, model, state, 0.0, "provider_recovered")

    def record_failure(self, provider: str, model: str) -> CircuitDecision:
        if not self.settings.circuit_breaker_enabled:
            return CircuitDecision(True, provider, model, "disabled", 0, 0.0, "failure_ignored_disabled")
        with self._lock:
            state = self._states.setdefault(_key(provider, model), _CircuitState())
            state.consecutive_failures += 1
            should_open = (
                state.state == "half_open"
                or state.consecutive_failures >= self.settings.circuit_breaker_failure_threshold
            )
            if should_open:
                state.state = "open"
                state.opened_at = self.clock()
            state.half_open_probe_in_flight = False
            reason = "failure_threshold_reached" if should_open else "failure_recorded"
            retry_after = self.settings.circuit_breaker_cooldown_seconds if should_open else 0.0
            return self._decision(not should_open, provider, model, state, retry_after, reason)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                key: {
                    "state": value.state,
                    "consecutive_failures": value.consecutive_failures,
                    "opened_at": value.opened_at,
                    "half_open_probe_in_flight": value.half_open_probe_in_flight,
                }
                for key, value in self._states.items()
            }

    @staticmethod
    def _decision(
        allowed: bool,
        provider: str,
        model: str,
        state: _CircuitState,
        retry_after_seconds: float,
        reason: str,
    ) -> CircuitDecision:
        return CircuitDecision(
            allowed=allowed,
            provider=provider,
            model=model,
            state=state.state,
            consecutive_failures=state.consecutive_failures,
            retry_after_seconds=round(retry_after_seconds, 3),
            reason=reason,
        )


def _key(provider: str, model: str) -> str:
    return f"{provider.strip().lower()}:{model.strip()}"
