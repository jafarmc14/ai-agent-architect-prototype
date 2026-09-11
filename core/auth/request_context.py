from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str = ""
    name: str = ""
    role: str = "customer"
    tenant_id: str = "default"


@dataclass(frozen=True)
class RequestContext:
    session_id: str
    tenant_id: str = "default"
    user: AuthenticatedUser | None = None
    request_id: str = ""
    trace_id: str = ""

    @property
    def user_id(self) -> str | None:
        return self.user.user_id if self.user else None

    @property
    def role(self) -> str:
        return self.user.role if self.user else "anonymous"

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None


_request_context: ContextVar[RequestContext] = ContextVar(
    "request_context",
    default=RequestContext(session_id="anonymous"),
)
_scoped_request: ContextVar[bool] = ContextVar("scoped_database_request", default=False)


def is_request_scoped() -> bool:
    return _scoped_request.get()


def get_request_context() -> RequestContext:
    return _request_context.get()


def anonymous_context(session_id: str = "anonymous") -> RequestContext:
    return RequestContext(session_id=session_id)


@contextmanager
def request_context(context: RequestContext) -> Iterator[RequestContext]:
    if context.user and context.user.tenant_id != context.tenant_id:
        raise PermissionError("Authenticated tenant does not match request tenant")
    token = _request_context.set(context)
    scope_token = _scoped_request.set(True)
    try:
        yield context
    finally:
        _scoped_request.reset(scope_token)
        _request_context.reset(token)
