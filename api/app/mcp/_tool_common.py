"""Common MCP tool helpers."""

from __future__ import annotations

from collections.abc import Callable

from app.db import session_scope
from app.domain.errors import DomainError
from app.mcp.serializers import ToolErrorResponse, serialize_domain_error


def run_with_session(
    operation: Callable[..., object], /, *args: object, **kwargs: object
) -> object:
    """Run one domain operation in a transaction-scoped DB session."""

    with session_scope() as session:
        return operation(session, *args, **kwargs)


def capture_domain_error(exc: DomainError) -> ToolErrorResponse:
    """Convert a domain error into the Appendix C MCP error envelope."""

    return serialize_domain_error(exc)
