from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_active_guard: ContextVar[object | None] = ContextVar("active_resource_guard", default=None)


def active_resource_guard():
    return _active_guard.get()


@contextmanager
def resource_guard_context(guard) -> Iterator[object]:
    token = _active_guard.set(guard)
    try:
        yield guard
    finally:
        _active_guard.reset(token)
