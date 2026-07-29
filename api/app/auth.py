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

MCP OAuth (``docs/features/mcp_oauth.md``, F-103) adds a second exemption,
gated on whether ``/mcp``'s ``GoogleProvider`` is actually configured (see
``app.main._build_mcp_auth_provider``): see ``_MCP_OAUTH_UNPROTECTED_PREFIXES``
below.
"""

from __future__ import annotations

import hmac

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.logging import get_logger

logger = get_logger(__name__)

_UNPROTECTED_PREFIXES = ("/health",)

# Paths FastMCP's `GoogleProvider`/`OAuthProxy` serve themselves, confirmed by
# reading the installed `fastmcp`/`mcp` source rather than assumed (see
# `docs/features/mcp_oauth.md` F-103 and `app.main._build_mcp_auth_provider`):
#
# - `/.well-known/oauth-authorization-server` and
#   `/.well-known/oauth-protected-resource(/mcp)` — RFC 8414/9728 discovery
#   metadata (`mcp/server/auth/routes.py:create_auth_routes`,
#   `create_protected_resource_routes`).
# - `/register` — dynamic client registration, always enabled by `OAuthProxy`
#   (`fastmcp/server/auth/oauth_proxy/proxy.py`: "Always enable DCR").
# - `/authorize`, `/token` — the standard OAuth authorize/token endpoints
#   (same SDK routes module).
# - `/consent` — `OAuthProxy`'s own consent-screen route, unconditionally
#   registered in `OAuthProxy.get_routes`.
# - `/auth/callback` — the default `redirect_path` Google redirects back to
#   after the user signs in (`OAuthProxy.__init__`: `self._redirect_path`
#   defaults to `"/auth/callback"`; we don't override it).
#
# `/revoke` is deliberately NOT here: `GoogleProvider` never passes an
# `upstream_revocation_endpoint`, so `OAuthProxy` never registers it
# (`RevocationOptions(enabled=True)` only happens when that endpoint is set).
#
# A client has no bearer token of any kind — static or OAuth-issued — until
# it has been through this handshake, so these must be reachable without the
# static `APP_TOKEN` check. Once OAuth is configured, the actual `/mcp`
# tool-call traffic is also exempted here, but that does NOT mean `/mcp` goes
# unauthenticated: FastMCP wraps that route in its own `RequireAuthMiddleware`
# (`fastmcp/server/http.py`), which calls `verify_token` on the very same
# `SingleEmailTokenVerifier`-wrapped provider — so `/mcp` ends up gated by the
# Google-issued token instead of (not in addition to) the static one. This
# whole prefix set is skipped entirely when OAuth isn't configured, so `/mcp`
# for a deployment without Google OAuth set up keeps requiring the static
# bearer token exactly as before.
_MCP_OAUTH_UNPROTECTED_PREFIXES = (
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
    "/register",
    "/authorize",
    "/token",
    "/consent",
    "/auth/callback",
    "/mcp",
)


def _auth_error(authorization: str | None, token: str) -> str | None:
    """The auth-upgrade seam (supersedes spec §9's `require_auth`; see module docstring)."""

    if not authorization or not authorization.startswith("Bearer "):
        return "missing bearer token"
    candidate = authorization[len("Bearer ") :]
    if not hmac.compare_digest(candidate, token):
        return "invalid token"
    return None


class AuthMiddleware:
    """ASGI middleware enforcing the bearer token on every request but `/health`.

    When `/mcp` has its own Google OAuth provider configured (`oauth_enabled`),
    the OAuth-handshake paths and `/mcp` itself are additionally exempted from
    this static check — see `_MCP_OAUTH_UNPROTECTED_PREFIXES` above for why
    that's still safe. When `oauth_enabled` is `False` (the default, and the
    only behavior before this feature existed), those paths stay covered by
    the static bearer check exactly as before.
    """

    def __init__(self, app: ASGIApp, token: str, *, oauth_enabled: bool = False) -> None:
        self.app = app
        self.token = token
        self._unprotected_prefixes = _UNPROTECTED_PREFIXES + (
            _MCP_OAUTH_UNPROTECTED_PREFIXES if oauth_enabled else ()
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(self._unprotected_prefixes):
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
