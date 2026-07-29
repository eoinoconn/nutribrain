"""Auth plumbing for the `/mcp` OAuth surface (see docs/features/mcp_oauth.md).

F-101 lives here: a Postgres-backed `AsyncKeyValue` adapter for FastMCP's
`GoogleProvider(client_storage=...)`. Later tasks (F-102/F-103) add the
email-allow-list token verifier and the actual `main.py` wiring; this package
intentionally does not import or get imported by `app.main` yet.
"""

from __future__ import annotations

from app.mcp_auth.storage import PostgresKeyValueStore

__all__ = ["PostgresKeyValueStore"]
