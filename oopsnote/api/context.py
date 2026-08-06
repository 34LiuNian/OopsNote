"""Request-scoped identity and workspace context."""

from __future__ import annotations

from dataclasses import dataclass
from contextvars import ContextVar, Token
from typing import Any

from fastapi import Request

from oopsnote.core import Principal, WorkspaceContext, WorkspaceStores


@dataclass(frozen=True, slots=True)
class RequestContext:
    principal: Principal
    workspace: WorkspaceContext
    stores: WorkspaceStores


_current_context: ContextVar[RequestContext | None] = ContextVar(
    "oopsnote_request_context",
    default=None,
)


def activate_request_context(context: RequestContext) -> Token[RequestContext | None]:
    return _current_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _current_context.reset(token)


def current_request_context() -> RequestContext | None:
    return _current_context.get()


def get_request_context(request: Request) -> RequestContext:
    """Return middleware-resolved context or fail closed for an unscoped call."""
    context: Any = getattr(request.state, "oopsnote_context", None)
    if not isinstance(context, RequestContext):
        raise RuntimeError("request has no authenticated workspace context")
    return context
