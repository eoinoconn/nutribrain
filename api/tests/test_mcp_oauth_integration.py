"""End-to-end integration tests for `/mcp`'s OAuth enforcement (F-104).

Everything F-104 needs to cover already has narrow unit coverage elsewhere:

- `tests/test_auth_mcp_oauth_prefixes.py` unit-tests `AuthMiddleware` directly
  against a stub Starlette app (not the real `/mcp` mount).
- `tests/test_mcp_auth_wiring.py` unit-tests `_build_mcp_auth_provider()` and
  the `SingleEmailTokenVerifier` reach-around in isolation, mocking only the
  innermost Google-calling verifier.
- `tests/test_mcp_oauth_settings.py` covers the all-or-nothing settings
  validation.

None of those drive an actual HTTP request through the real, mounted `/mcp`
ASGI app with a real `GoogleProvider` configured. That's this module's job:
prove the *whole chain* — FastMCP's own auth-enforcement middleware
(`RequireAuthMiddleware` from `fastmcp/server/auth/middleware.py`, wrapping
`mcp.server.auth.middleware.bearer_auth.RequireAuthMiddleware`) sitting in
front of `GoogleProvider` (an `OAuthProxy`), which delegates to our
`SingleEmailTokenVerifier` reach-around, which delegates to a (mocked)
Google-calling verifier — is actually wired together on the real mounted app,
not just correct link-by-link.

**Boundary chosen, and why:** a real HTTP round trip through `/mcp`, but
*not* a full browser-driven DCR + `/authorize` + Google-consent + `/token`
handshake (driving that through `TestClient` would mean scripting Google's
consent redirect, which is explicitly out of scope — we mock Google). Instead
of a full handshake, this module mints a FastMCP-issued access token using
the exact same primitives `OAuthProxy.exchange_authorization_code` itself
uses when a real handshake completes (`fastmcp/server/auth/oauth_proxy/proxy.py`
around line 1188 on): store an `UpstreamTokenSet` (the "Google" side) in
`provider._upstream_token_store`, sign a FastMCP JWT via `provider.jwt_issuer`,
and record the JTI-to-upstream-token mapping in `provider._jti_mapping_store`.
Then a real `Authorization: Bearer <that JWT>` header is sent to a real
`POST /mcp`. This exercises FastMCP's actual token-swap logic in
`OAuthProxy.load_access_token` (JWT verify -> JTI lookup -> upstream token
lookup -> `self._token_validator.verify_token(upstream_access_token)`) end to
end; only the innermost Google-calling verifier
(`provider._token_validator._inner.verify_token`, i.e. what would otherwise
call `https://oauth2.googleapis.com/tokeninfo`) is mocked, exactly as
`test_mcp_auth_wiring.py` already does for its narrower assertion. This was
verified against the installed `fastmcp`/`mcp` source (not assumed) before
being relied on here.

Each test builds a *fresh* `FastMCP`/`FastAPI` app inside the test itself
(mirroring `app.main.create_app`'s middleware wiring) rather than reusing the
process-wide `app.main.app` singleton, because that singleton is built once
at import time with OAuth unconfigured (see
`test_mcp_auth_wiring.test_module_level_mcp_has_no_auth_provider_in_this_test_environment`).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import FastMCP
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.oauth_proxy.models import JTIMapping, UpstreamTokenSet
from fastmcp.server.auth.oauth_proxy.proxy import OAuthProxy

from app import settings as settings_module
from app.auth import AuthMiddleware
from app.main import _build_mcp_auth_provider
from app.mcp import register_all_tools
from app.mcp_auth import SingleEmailTokenVerifier

ALLOWED_EMAIL = "allowed@example.com"
_APP_TOKEN = "static-app-token-for-oauth-integration-test"


def _configure_oauth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire up OAuth settings the same way `test_mcp_auth_wiring.py` does.

    `mcp_public_base_url` must be an `https://` (or localhost) URL — the
    installed `mcp` SDK's `validate_issuer_url` rejects anything else, even
    in tests, so `http://testserver` (TestClient's default host) doesn't
    work here; `http://localhost:8000` matches the existing convention in
    `test_mcp_auth_wiring.py`.
    """

    monkeypatch.setattr(settings_module.settings, "google_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings_module.settings, "google_oauth_client_secret", "test-secret")
    monkeypatch.setattr(settings_module.settings, "mcp_allowed_email", ALLOWED_EMAIL)
    monkeypatch.setattr(settings_module.settings, "mcp_public_base_url", "http://localhost:8000")
    monkeypatch.setattr(settings_module.settings, "app_token", _APP_TOKEN)


async def _issue_fastmcp_access_token(provider: OAuthProxy, *, upstream_access_token: str) -> str:
    """Mint a real FastMCP-issued access token bound to a fake upstream token.

    Mirrors what `OAuthProxy.exchange_authorization_code` does when a real
    `/token` exchange completes (see module docstring): store an
    `UpstreamTokenSet` standing in for what Google would have returned, sign
    a FastMCP JWT via the real `jwt_issuer`, and record the JTI mapping. The
    token returned here is what a real MCP client would present as
    `Authorization: Bearer <token>`.
    """

    access_jti = uuid.uuid4().hex
    upstream_token_id = uuid.uuid4().hex

    upstream_token_set = UpstreamTokenSet(
        upstream_token_id=upstream_token_id,
        access_token=upstream_access_token,
        refresh_token=None,
        refresh_token_expires_at=None,
        expires_at=time.time() + 3600,
        token_type="Bearer",
        scope="openid",
        client_id="test-mcp-client",
        created_at=time.time(),
        raw_token_data={},
    )
    await provider._upstream_token_store.put(
        key=upstream_token_id, value=upstream_token_set, ttl=3600
    )

    fastmcp_token = provider.jwt_issuer.issue_access_token(
        client_id="test-mcp-client",
        scopes=["openid"],
        jti=access_jti,
        expires_in=3600,
    )

    await provider._jti_mapping_store.put(
        key=access_jti,
        value=JTIMapping(
            jti=access_jti, upstream_token_id=upstream_token_id, created_at=time.time()
        ),
        ttl=3600,
    )

    return fastmcp_token


def _build_oauth_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Build a fresh FastAPI app wired exactly like `app.main.create_app`,
    but around a brand-new `FastMCP` instance so each test gets its own
    `GoogleProvider`/`OAuthProxy` state rather than sharing the process-wide
    `app.main.mcp` singleton (which is built once, at import time, before
    OAuth settings exist for the test suite).
    """

    _configure_oauth_settings(monkeypatch)
    provider = _build_mcp_auth_provider()
    assert provider is not None, "OAuth settings above must produce a real GoogleProvider"

    mcp = FastMCP("nutribrain-oauth-integration-test", auth=provider)
    register_all_tools(mcp)
    mcp_app = mcp.http_app(path="/mcp")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp_app.lifespan(app):
            yield

    app = FastAPI(title="nutribrain-oauth-integration-test", lifespan=lifespan)
    app.add_middleware(
        AuthMiddleware,
        token=settings_module.settings.app_token or "",
        oauth_enabled=mcp.auth is not None,
    )

    @app.get("/api/anything")
    def _api_anything() -> dict[str, str]:
        return {"ok": "true"}

    app.mount("/", mcp_app)
    app.state.mcp_provider = provider
    return app


def _mock_inner_verifier(provider: OAuthProxy, *, email: str, email_verified: bool = True) -> None:
    """Mock only the innermost Google-calling verifier, per the brief.

    `provider._token_validator` is `SingleEmailTokenVerifier` (F-102), set by
    the real `_build_mcp_auth_provider` reach-around (F-103) — not re-mocked
    here, since that link is already covered by `test_mcp_auth_wiring.py`.
    Only `._inner` (what would otherwise call Google's tokeninfo endpoint) is
    replaced, so this test exercises the real allow-list check.
    """

    validator = provider._token_validator
    assert isinstance(validator, SingleEmailTokenVerifier)

    async def _fake_verify(token: str) -> AccessToken | None:
        return AccessToken(
            token=token,
            client_id="google-sub",
            scopes=["openid"],
            claims={"email": email, "email_verified": email_verified},
        )

    validator._inner.verify_token = _fake_verify  # type: ignore[method-assign]


def _mcp_headers(bearer: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json, text/event-stream"}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


_INITIALIZE_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "nutribrain-oauth-integration-test", "version": "0.0.1"},
    },
}


@pytest.mark.asyncio
async def test_allowed_email_token_is_accepted_by_fastmcps_own_auth_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_oauth_app(monkeypatch)
    provider = app.state.mcp_provider
    _mock_inner_verifier(provider, email=ALLOWED_EMAIL)

    token = await _issue_fastmcp_access_token(
        provider, upstream_access_token="fake-google-token-ok"
    )

    with TestClient(app) as client:
        response = client.post("/mcp", json=_INITIALIZE_BODY, headers=_mcp_headers(token))

    assert response.status_code == 200
    # A 200 here means the request cleared `RequireAuthMiddleware` and reached
    # the real MCP session/initialize handler — i.e. FastMCP's own auth layer
    # (not `AuthMiddleware`, which exempts all of `/mcp` once OAuth is
    # configured — see `app/auth.py`) accepted the Google-issued token.
    assert '"protocolVersion"' in response.text


@pytest.mark.asyncio
async def test_wrong_email_token_is_rejected_by_fastmcps_own_auth_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_oauth_app(monkeypatch)
    provider = app.state.mcp_provider
    _mock_inner_verifier(provider, email="someone-else@example.com")

    token = await _issue_fastmcp_access_token(
        provider, upstream_access_token="fake-google-token-wrong"
    )

    with TestClient(app) as client:
        response = client.post("/mcp", json=_INITIALIZE_BODY, headers=_mcp_headers(token))

    assert response.status_code == 401
    # This exact body shape (`{"error": "invalid_token", ...}` plus a
    # `WWW-Authenticate` header) comes from FastMCP's
    # `RequireAuthMiddleware._send_auth_error`
    # (`fastmcp/server/auth/middleware.py`) — not from `app.auth.AuthMiddleware`,
    # whose rejection body is `{"detail": "..."}` with no `WWW-Authenticate`
    # header (see `tests/test_auth_mcp_oauth_prefixes.py`). Confirming this
    # shape proves the rejection happened in FastMCP's layer.
    body = response.json()
    assert body["error"] == "invalid_token"
    assert "detail" not in body
    assert "www-authenticate" in {k.lower() for k in response.headers}


@pytest.mark.asyncio
async def test_unverified_email_token_is_rejected_by_fastmcps_own_auth_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_oauth_app(monkeypatch)
    provider = app.state.mcp_provider
    _mock_inner_verifier(provider, email=ALLOWED_EMAIL, email_verified=False)

    token = await _issue_fastmcp_access_token(
        provider, upstream_access_token="fake-google-token-unverified"
    )

    with TestClient(app) as client:
        response = client.post("/mcp", json=_INITIALIZE_BODY, headers=_mcp_headers(token))

    assert response.status_code == 401


def test_missing_bearer_token_is_rejected_by_fastmcps_own_auth_layer_not_authmiddleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/mcp` is in `AuthMiddleware`'s OAuth-only allowlist once OAuth is
    configured (`app/auth.py`'s `_MCP_OAUTH_UNPROTECTED_PREFIXES`), so a
    request with *no* bearer token at all must still be rejected — but by
    FastMCP's `RequireAuthMiddleware`, not by `AuthMiddleware`. Per RFC 6750
    §3.1 (see `fastmcp/server/auth/middleware.py`'s
    `RequireAuthMiddleware._send_missing_auth`), a *missing* Authorization
    header gets an empty 401 body with a bare `WWW-Authenticate: Bearer`
    header — distinct in shape from both `AuthMiddleware`'s
    `{"detail": "missing bearer token"}` JSON body and from the
    invalid-token JSON shape asserted in the wrong-email test above. Getting
    exactly this shape confirms `AuthMiddleware` stepped out of the way and
    FastMCP's own layer did the rejecting.
    """

    app = _build_oauth_app(monkeypatch)

    with TestClient(app) as client:
        response = client.post("/mcp", json=_INITIALIZE_BODY, headers=_mcp_headers(None))

    assert response.status_code == 401
    assert response.text == ""
    assert "www-authenticate" in {k.lower() for k in response.headers}


def test_api_star_traffic_still_requires_static_bearer_token_with_oauth_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard (the "widening the allowlist too far" case called out
    in F-104): with OAuth fully configured on the real app, `/api/*` traffic
    must be completely unaffected — still gated by the static `APP_TOKEN`
    bearer check in `AuthMiddleware`, not by anything OAuth-related.
    """

    app = _build_oauth_app(monkeypatch)

    with TestClient(app) as client:
        unauthenticated = client.get("/api/anything")
        wrong_token = client.get("/api/anything", headers={"Authorization": "Bearer wrong"})
        authenticated = client.get(
            "/api/anything", headers={"Authorization": f"Bearer {_APP_TOKEN}"}
        )

    assert unauthenticated.status_code == 401
    assert wrong_token.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json() == {"ok": "true"}
