import threading
import time
from collections import defaultdict, deque
from typing import Any


class LoginThrottle:
    """In-memory brute-force protection for the login endpoint.

    - Per-username lockout: N consecutive failures locks the account for a
      cooldown window.
    - Per-IP sliding window: caps total failures from one source address.
    Thread-safe for the single-process uvicorn deployment. Counters reset on
    process restart and are not shared across multiple app instances.
    """

    def __init__(
        self,
        max_failures: int = 5,
        lockout_seconds: int = 900,
        ip_max_failures: int = 20,
        ip_window_seconds: int = 3600,
    ) -> None:
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self.ip_max_failures = ip_max_failures
        self.ip_window_seconds = ip_window_seconds
        self._lock = threading.RLock()
        self._username_failures: dict[str, int] = {}
        self._username_locked_until: dict[str, float] = {}
        self._ip_events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, username: str, ip: str) -> int | None:
        """Return retry-after seconds if the login is blocked, else None."""
        with self._lock:
            now = time.time()
            locked_until = self._username_locked_until.get(username)
            if locked_until and locked_until > now:
                return int(locked_until - now) + 1
            events = self._ip_events[ip]
            while events and events[0] < now - self.ip_window_seconds:
                events.popleft()
            if len(events) >= self.ip_max_failures:
                return int(self.ip_window_seconds)
            return None

    def record_failure(self, username: str, ip: str) -> None:
        with self._lock:
            now = time.time()
            failures = self._username_failures.get(username, 0) + 1
            self._username_failures[username] = failures
            if failures >= self.max_failures:
                self._username_locked_until[username] = now + self.lockout_seconds
                self._username_failures[username] = 0
            self._ip_events[ip].append(now)

    def record_success(self, username: str) -> None:
        with self._lock:
            self._username_failures.pop(username, None)
            self._username_locked_until.pop(username, None)

    def reset(self) -> None:
        with self._lock:
            self._username_failures.clear()
            self._username_locked_until.clear()
            self._ip_events.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "username_failures": dict(self._username_failures),
                "username_locked_until": dict(self._username_locked_until),
                "ip_events": {ip: len(events) for ip, events in self._ip_events.items()},
            }


login_throttle = LoginThrottle()