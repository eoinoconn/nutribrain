"""Tests for `_build_mcp_auth_provider` (F-103): the `/mcp` Google OAuth wiring.

See `docs/features/mcp_oauth.md` F-103 and `app.main._build_mcp_auth_provider`.

The important case here (per that function's docstring) is the private-attribute
reach-around: `GoogleProvider` has no public constructor seam to inject a wrapped
token verifier, so `_build_mcp_auth_provider` reaches into `provider._token_validator`
after construction and swaps in `SingleEmailTokenVerifier`. If a future `fastmcp`
upgrade renames or removes that attribute, this must fail loudly (an `AttributeError`
from a real `GoogleProvider` instance, not a mock) rather than silently leaving
`/mcp` open to any Google account.
"""

from __future__ import annotations

import pytest
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider

from app import settings as settings_module
from app.main import _build_mcp_auth_provider
from app.mcp_auth import SingleEmailTokenVerifier

_OAUTH_FIELDS = (
    "google_oauth_client_id",
    "google_oauth_client_secret",
    "mcp_allowed_email",
    "mcp_public_base_url",
)


def _clear_oauth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for field in _OAUTH_FIELDS:
        monkeypatch.setattr(settings_module.settings, field, None)


def _configure_oauth_settings(monkeypatch: pytest.MonkeyPatch, allowed_email: str) -> None:
    _clear_oauth_settings(monkeypatch)
    monkeypatch.setattr(settings_module.settings, "google_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings_module.settings, "google_oauth_client_secret", "test-secret")
    monkeypatch.setattr(settings_module.settings, "mcp_allowed_email", allowed_email)
    monkeypatch.setattr(settings_module.settings, "mcp_public_base_url", "http://localhost:8000")


def test_returns_none_when_oauth_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_oauth_settings(monkeypatch)

    assert _build_mcp_auth_provider() is None


def test_module_level_mcp_has_no_auth_provider_in_this_test_environment() -> None:
    """No Google OAuth env vars are set for the test suite (see `.env.example`),
    so the process-wide `app.main.mcp` (built once, at import time) must have
    been constructed with `auth=None` — i.e. `/mcp` behaves exactly as it did
    before this feature existed. `tests/test_auth.py`'s `TestMcpAuth` cases
    exercise the resulting behavior end-to-end; this just pins the underlying
    cause.
    """

    from app.main import mcp

    assert mcp.auth is None


def test_returns_a_real_google_provider_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_oauth_settings(monkeypatch, "me@example.com")

    provider = _build_mcp_auth_provider()

    assert isinstance(provider, GoogleProvider)


@pytest.mark.asyncio
async def test_reach_around_wraps_the_real_provider_verifier_with_single_email_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The safety-net test called out in `_build_mcp_auth_provider`'s docstring.

    Deliberately does not mock `GoogleProvider` or `provider._token_validator` —
    it uses the real, installed `fastmcp` provider so that if a `fastmcp` upgrade
    ever renames/removes `_token_validator`, this test fails with an `AttributeError`
    instead of silently no-oping.
    """

    _configure_oauth_settings(monkeypatch, "allowed@example.com")

    provider = _build_mcp_auth_provider()
    assert provider is not None

    # This is the actual reach-around assertion: the attribute FastMCP's
    # OAuthProxy uses for every verify_token() call site must now be our wrapper.
    assert isinstance(provider._token_validator, SingleEmailTokenVerifier)

    # Drive verify_token() end-to-end through the real attribute FastMCP calls,
    # faking only the network-calling innermost GoogleTokenVerifier so no real
    # HTTP request to Google is made.
    wrapper = provider._token_validator

    async def _fake_verify_wrong_email(token: str) -> AccessToken | None:
        return AccessToken(
            token=token,
            client_id="google-sub",
            scopes=["openid"],
            claims={"email": "someone-else@example.com", "email_verified": True},
        )

    monkeypatch.setattr(wrapper._inner, "verify_token", _fake_verify_wrong_email)
    assert await provider._token_validator.verify_token("some-token") is None

    async def _fake_verify_allowed_email(token: str) -> AccessToken | None:
        return AccessToken(
            token=token,
            client_id="google-sub",
            scopes=["openid"],
            claims={"email": "Allowed@Example.com", "email_verified": True},
        )

    monkeypatch.setattr(wrapper._inner, "verify_token", _fake_verify_allowed_email)
    result = await provider._token_validator.verify_token("some-token")
    assert result is not None
    assert result.claims["email"] == "Allowed@Example.com"
