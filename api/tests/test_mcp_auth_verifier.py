"""Tests for the single-email allow-list token verifier (F-102).

See `docs/features/mcp_oauth.md` ("Single-user enforcement" / F-102) and
`app/mcp_auth/verifier.py`. These tests use a small fake inner verifier —
no network calls, no real Google endpoints.
"""

from __future__ import annotations

import pytest
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

from app.mcp_auth.verifier import SingleEmailTokenVerifier

ALLOWED_EMAIL = "alice@example.com"


def _access_token(email: str | None, email_verified: object) -> AccessToken:
    return AccessToken(
        token="raw-token",
        client_id="google-sub-123",
        scopes=["openid"],
        claims={"email": email, "email_verified": email_verified},
    )


class _FakeInnerVerifier(TokenVerifier):
    """Stands in for `GoogleTokenVerifier` without hitting the network."""

    def __init__(self, result: AccessToken | None) -> None:
        super().__init__(required_scopes=["openid"])
        self._result = result

    async def verify_token(self, token: str) -> AccessToken | None:
        return self._result


@pytest.mark.asyncio
async def test_matching_email_any_case_passes_through_unchanged() -> None:
    inner_result = _access_token("Alice@Example.com", True)
    verifier = SingleEmailTokenVerifier(
        inner=_FakeInnerVerifier(inner_result), allowed_email=ALLOWED_EMAIL
    )

    result = await verifier.verify_token("some-token")

    assert result is inner_result


@pytest.mark.asyncio
async def test_non_matching_email_is_rejected() -> None:
    inner_result = _access_token("mallory@example.com", True)
    verifier = SingleEmailTokenVerifier(
        inner=_FakeInnerVerifier(inner_result), allowed_email=ALLOWED_EMAIL
    )

    result = await verifier.verify_token("some-token")

    assert result is None


@pytest.mark.asyncio
async def test_unverified_email_is_rejected_even_if_matching() -> None:
    for falsy_verified in (False, None, ""):
        inner_result = _access_token(ALLOWED_EMAIL, falsy_verified)
        verifier = SingleEmailTokenVerifier(
            inner=_FakeInnerVerifier(inner_result), allowed_email=ALLOWED_EMAIL
        )

        result = await verifier.verify_token("some-token")

        assert result is None


@pytest.mark.asyncio
async def test_missing_email_claim_is_rejected() -> None:
    inner_result = _access_token(None, True)
    verifier = SingleEmailTokenVerifier(
        inner=_FakeInnerVerifier(inner_result), allowed_email=ALLOWED_EMAIL
    )

    result = await verifier.verify_token("some-token")

    assert result is None


@pytest.mark.asyncio
async def test_inner_verifier_returning_none_stays_none() -> None:
    verifier = SingleEmailTokenVerifier(inner=_FakeInnerVerifier(None), allowed_email=ALLOWED_EMAIL)

    result = await verifier.verify_token("expired-or-invalid-token")

    assert result is None
