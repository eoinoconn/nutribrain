"""Auth plumbing for the `/mcp` OAuth surface (see docs/features/mcp_oauth.md).

F-101 lives here: a Postgres-backed `AsyncKeyValue` adapter for FastMCP's
`GoogleProvider(client_storage=...)`. F-102 adds `SingleEmailTokenVerifier`,
the email-allow-list wrapper around Google's token verifier. F-103 does the
actual `main.py` wiring; this package intentionally does not import or get
imported by `app.main` yet.
"""

from __future__ import annotations

from app.mcp_auth.storage import PostgresKeyValueStore
from app.mcp_auth.verifier import SingleEmailTokenVerifier

__all__ = ["PostgresKeyValueStore", "SingleEmailTokenVerifier"]
