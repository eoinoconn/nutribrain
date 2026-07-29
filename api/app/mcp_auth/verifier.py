"""Single-email allow-list wrapper around a Google token verifier (F-102).

Background (`docs/features/mcp_oauth.md`, "Single-user enforcement" / F-102):
FastMCP's `GoogleProvider` verifies Google OAuth tokens via its internal
`GoogleTokenVerifier` (`fastmcp.server.auth.providers.google`), which returns
an `AccessToken` whose `claims` include `email` and `email_verified`. That
verifier does not restrict *which* Google account may authenticate — any
Google account that completes the consent screen gets a valid token. Since
NutriBrain is a single-user app (`CLAUDE.md`: "exactly one user and no
`user_id`"), this module adds the missing enforcement: wrap the inner
verifier and reject any token whose email doesn't match the one configured
allowed address, or whose email Google hasn't verified.

This module wraps rather than subclasses `GoogleTokenVerifier` so it works
with any `TokenVerifier` whose `AccessToken.claims` follow the same
`email`/`email_verified` shape — it has no import-time dependency on
`fastmcp.server.auth.providers.google` and none on `app.settings`; the
allowed email is a plain constructor argument. Wiring this into
`GoogleProvider`/`FastMCP(auth=...)` is F-103's job, not this module's.
"""

from __future__ import annotations

from fastmcp.server.auth.auth import AccessToken, TokenVerifier

from app.logging import get_logger

logger = get_logger(__name__)


class SingleEmailTokenVerifier(TokenVerifier):
    """Wraps a `TokenVerifier`, accepting only one verified email address.

    Composition, not inheritance: `inner` does the real work of validating
    the token (e.g. calling Google's tokeninfo endpoint); this class only
    adds the single-user allow-list check on top of whatever `AccessToken`
    the inner verifier produces. A token is accepted only if all of the
    following hold:

    - the inner verifier returns a non-`None` `AccessToken`,
    - `claims["email_verified"]` is truthy, and
    - `claims["email"]` case-insensitively equals the configured
      `allowed_email`.

    Any other outcome returns `None` (the same "invalid token" signal
    `TokenVerifier.verify_token` uses for an expired/malformed token) —
    rejection is never distinguished from any other kind of invalid token,
    so no caller can learn *why* a token was rejected beyond a server-side
    log line.
    """

    def __init__(self, inner: TokenVerifier, allowed_email: str) -> None:
        """Initialize the wrapper.

        Args:
            inner: The token verifier to delegate real verification to
                (e.g. `GoogleTokenVerifier`).
            allowed_email: The one email address permitted to authenticate,
                compared case-insensitively. Passed in by the caller (F-103
                reads it from `app.settings`) rather than read from settings
                directly here, keeping this module's dependencies minimal.
        """
        super().__init__(required_scopes=inner.required_scopes)
        self._inner = inner
        self._allowed_email = allowed_email

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify `token` via `inner`, then enforce the single-user allow-list."""

        access_token = await self._inner.verify_token(token)
        if access_token is None:
            return None

        email = access_token.claims.get("email")
        email_verified = access_token.claims.get("email_verified")

        if not email_verified:
            logger.warning("mcp_auth_rejected", reason="email_not_verified")
            return None

        if not isinstance(email, str) or email.lower() != self._allowed_email.lower():
            logger.warning("mcp_auth_rejected", reason="email_not_allowed")
            return None

        return access_token
