"""Tests for `AuthMiddleware`'s conditional MCP-OAuth prefix exemptions (F-103/F-104).

See `docs/features/mcp_oauth.md` and `app/auth.py` (`_MCP_OAUTH_UNPROTECTED_PREFIXES`).
These exercise `AuthMiddleware` directly against a minimal ASGI app rather than the
full `app.main.app`, so both the "OAuth configured" and "OAuth not configured" cases
can be tested without actually standing up a `GoogleProvider`.

Regression guard: this is exactly the surface that would silently widen if
`_MCP_OAUTH_UNPROTECTED_PREFIXES` (or the `oauth_enabled` gating) is ever loosened
past what F-103 intended — `/api/*`-equivalent traffic must stay protected in both
cases, and the OAuth-only exemptions must disappear entirely when OAuth isn't
configured.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.auth import AuthMiddleware

TOKEN = "s3cr3t"

_OAUTH_ONLY_PATHS = (
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource/mcp",
    "/register",
    "/authorize",
    "/token",
    "/consent",
    "/auth/callback",
    "/mcp",
)


async def _ok(request):  # type: ignore[no-untyped-def]
    return PlainTextResponse("ok")


def _make_client(*, oauth_enabled: bool) -> TestClient:
    inner = Starlette(routes=[Route("/{path:path}", _ok)])
    wrapped = AuthMiddleware(inner, token=TOKEN, oauth_enabled=oauth_enabled)
    return TestClient(wrapped)


@pytest.mark.parametrize("path", _OAUTH_ONLY_PATHS)
def test_oauth_paths_unprotected_when_oauth_enabled(path: str) -> None:
    client = _make_client(oauth_enabled=True)

    response = client.get(path)

    assert response.status_code == 200


@pytest.mark.parametrize("path", _OAUTH_ONLY_PATHS)
def test_oauth_paths_still_require_bearer_token_when_oauth_disabled(path: str) -> None:
    client = _make_client(oauth_enabled=False)

    response = client.get(path)

    assert response.status_code == 401


def test_health_stays_unprotected_regardless_of_oauth_flag() -> None:
    for oauth_enabled in (True, False):
        client = _make_client(oauth_enabled=oauth_enabled)

        response = client.get("/health")

        assert response.status_code == 200


def test_non_oauth_traffic_still_requires_bearer_token_when_oauth_enabled() -> None:
    client = _make_client(oauth_enabled=True)

    response = client.get("/api/anything")

    assert response.status_code == 401

    response = client.get("/api/anything", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200


def test_non_oauth_traffic_still_requires_bearer_token_when_oauth_disabled() -> None:
    client = _make_client(oauth_enabled=False)

    response = client.get("/api/anything")

    assert response.status_code == 401

    response = client.get("/api/anything", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 200
