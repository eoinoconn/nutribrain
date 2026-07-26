"""Bearer-token auth (T-030).

Spec §9 shows a per-route ``Depends(require_auth)`` and names it "the seam
for future Google OAuth ... zero route code touched during upgrade." G7
(``docs/decisions.md`` D-003) found that seam doesn't work: FastAPI's
``dependencies=[...]`` never runs for a mounted ASGI sub-application (the
FastMCP app at ``/mcp``), so a per-route dependency protects nothing there.
Enforcement instead lives entirely in ``AuthMiddleware``, wrapping the whole
ASGI stack so both the FastAPI routes and the FastMCP mount are covered by
one check. There is no ``require_auth`` function — a route-level dependency
would be redundant at best and misleading at worst, implying per-route auth
that middleware already guarantees. ``_auth_error`` is the actual seam: swap
its body for session-cookie or JWT validation and every route stays covered.
"""

from __future__ import annotations

import hmac

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.logging import get_logger

logger = get_logger(__name__)

_UNPROTECTED_PREFIXES = ("/health",)


def _auth_error(authorization: str | None, token: str) -> str | None:
    """The auth-upgrade seam (supersedes spec §9's `require_auth`; see module docstring)."""

    if not authorization or not authorization.startswith("Bearer "):
        return "missing bearer token"
    candidate = authorization[len("Bearer ") :]
    if not hmac.compare_digest(candidate, token):
        return "invalid token"
    return None


class AuthMiddleware:
    """ASGI middleware enforcing the bearer token on every request but `/health`."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(_UNPROTECTED_PREFIXES):
            await self.app(scope, receive, send)
            return

        authorization = Headers(scope=scope).get("authorization")
        error = _auth_error(authorization, self.token)
        if error is not None:
            logger.warning("auth_failure", reason=error, path=scope["path"])
            response = JSONResponse({"detail": error}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
