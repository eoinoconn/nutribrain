"""Request logging middleware (T-032).

Binds ``request_id`` to every request via structlog context variables.
Logs requests that exceed 500ms. Does not log successful reads.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

from app.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    """ASGI middleware that binds request_id and logs slow requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        method = scope.get("method", "")
        path = scope.get("path", "")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: dict) -> None:  # type: ignore[type-arg]
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status")
            await send(message)

        await self.app(scope, receive, send_wrapper)  # type: ignore[arg-type]

        duration_ms = (time.perf_counter() - start) * 1000

        # Log slow requests (>500ms) regardless of method
        if duration_ms > 500:
            logger.warning(
                "slow_request",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 1),
            )
        # Log mutations (non-GET) but not successful reads
        elif method not in ("GET", "HEAD", "OPTIONS"):
            logger.info(
                "request_complete",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration_ms, 1),
            )
