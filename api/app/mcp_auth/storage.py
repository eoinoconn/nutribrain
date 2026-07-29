"""Postgres-backed `AsyncKeyValue` adapter for FastMCP's `client_storage`.

Background (`docs/features/mcp_oauth.md`, "Motivation" / F-101): FastMCP's
`GoogleProvider` persists OAuth-proxy state (registered DCR clients, encrypted
upstream tokens, authorization codes, refresh-token metadata, ...) through a
pluggable `client_storage: AsyncKeyValue`. Left at its default, that's an
encrypted file store under a local data directory — fine on a laptop, but
Render's filesystem is ephemeral across deploys, so every deploy would
silently revoke Claude's registration and force the OAuth dance again.
Postgres is already the one source of truth for this app, so this module
backs the same protocol with the `mcp_oauth_kv` table instead.

This adapter implements the full `key_value.aio.protocols.AsyncKeyValue`
protocol (get/put/delete/ttl plus their `_many` bulk variants), since that's
the type `GoogleProvider(client_storage=...)` is annotated to accept. In
practice `OAuthProxy` (see
`fastmcp/server/auth/oauth_proxy/proxy.py`, via its internal
`PydanticAdapter` wrapper) only ever calls the singular `get`/`put`/`delete`/
`ttl` — the bulk variants exist here for protocol conformance and are
exercised by this module's own tests, not by any current FastMCP code path.

This module owns a dedicated async SQLAlchemy engine (`postgresql+psycopg`
supports asyncio natively; no new dependency was needed — `psycopg` and
`sqlalchemy` are already direct dependencies). It intentionally does not
share the app's sync `app.db.engine.engine`, since that engine is configured
and used exclusively for sync `Session` access elsewhere in the app.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, SupportsFloat, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.models import McpOAuthKV
from app.settings import settings

_DEFAULT_COLLECTION = "default"


def _resolve_collection(collection: str | None) -> str:
    """`AsyncKeyValue` treats `collection=None` as "the default collection"."""

    return collection if collection is not None else _DEFAULT_COLLECTION


def _ttl_to_expires_at(ttl: SupportsFloat | None) -> datetime | None:
    if ttl is None:
        return None
    return datetime.now(UTC) + timedelta(seconds=float(ttl))


class PostgresKeyValueStore:
    """`AsyncKeyValue`-conformant store backed by the `mcp_oauth_kv` table.

    Expired entries are filtered lazily on read (`expires_at IS NULL OR
    expires_at > now()`) rather than actively swept by a background job —
    simpler, and correct: nothing reads or lists expired rows, and a stale
    row is silently replaced (or deleted) the next time its key is written or
    deleted. Orphaned expired rows are otherwise harmless and can be reaped
    later (see F-108 revocation notes) rather than needing a cron job now.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: AsyncEngine | None = None,
    ) -> None:
        # G6 (docs/decisions.md, mirrored from app/db/engine.py): Neon's free
        # tier scales to zero and kills idle connections, so this async engine
        # needs the same pool_pre_ping/pool_recycle guard the sync engine has
        # — without it, a connection killed by Neon's scale-to-zero hangs
        # until a TCP-level timeout instead of transparently reconnecting.
        self._engine: AsyncEngine = engine or create_async_engine(
            database_url or settings.database_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    async def aclose(self) -> None:
        """Dispose of the underlying engine's connection pool."""

        await self._engine.dispose()

    async def get(self, key: str, *, collection: str | None = None) -> dict[str, Any] | None:
        value, _ttl = await self.ttl(key, collection=collection)
        return value

    async def ttl(
        self, key: str, *, collection: str | None = None
    ) -> tuple[dict[str, Any] | None, float | None]:
        coll = _resolve_collection(collection)
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(McpOAuthKV.value, McpOAuthKV.expires_at).where(
                        McpOAuthKV.collection == coll,
                        McpOAuthKV.key == key,
                    )
                )
            ).first()
        return _live_value_and_ttl(None if row is None else (row.value, row.expires_at))

    async def put(
        self,
        key: str,
        value: Mapping[str, Any],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        coll = _resolve_collection(collection)
        expires_at = _ttl_to_expires_at(ttl)
        stmt = pg_insert(McpOAuthKV).values(
            collection=coll, key=key, value=dict(value), expires_at=expires_at
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[McpOAuthKV.collection, McpOAuthKV.key],
            set_={"value": stmt.excluded.value, "expires_at": stmt.excluded.expires_at},
        )
        async with self._sessionmaker() as session:
            await session.execute(stmt)
            await session.commit()

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        coll = _resolve_collection(collection)
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(McpOAuthKV).where(McpOAuthKV.collection == coll, McpOAuthKV.key == key)
            )
            await session.commit()
        return bool(cast(CursorResult[Any], result).rowcount)

    async def get_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[dict[str, Any] | None]:
        pairs = await self.ttl_many(keys, collection=collection)
        return [value for value, _ttl in pairs]

    async def ttl_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[tuple[dict[str, Any] | None, float | None]]:
        coll = _resolve_collection(collection)
        async with self._sessionmaker() as session:
            rows = (
                await session.execute(
                    select(McpOAuthKV.key, McpOAuthKV.value, McpOAuthKV.expires_at).where(
                        McpOAuthKV.collection == coll,
                        McpOAuthKV.key.in_(keys),
                    )
                )
            ).all()
        by_key = {row.key: (row.value, row.expires_at) for row in rows}
        return [_live_value_and_ttl(by_key.get(key)) for key in keys]

    async def put_many(
        self,
        keys: Sequence[str],
        values: Sequence[Mapping[str, Any]],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        coll = _resolve_collection(collection)
        expires_at = _ttl_to_expires_at(ttl)
        rows = [
            {"collection": coll, "key": key, "value": dict(value), "expires_at": expires_at}
            for key, value in zip(keys, values, strict=True)
        ]
        if not rows:
            return
        stmt = pg_insert(McpOAuthKV).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[McpOAuthKV.collection, McpOAuthKV.key],
            set_={"value": stmt.excluded.value, "expires_at": stmt.excluded.expires_at},
        )
        async with self._sessionmaker() as session:
            await session.execute(stmt)
            await session.commit()

    async def delete_many(self, keys: Sequence[str], *, collection: str | None = None) -> int:
        coll = _resolve_collection(collection)
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(McpOAuthKV).where(
                    McpOAuthKV.collection == coll,
                    McpOAuthKV.key.in_(keys),
                )
            )
            await session.commit()
        return int(cast(CursorResult[Any], result).rowcount)


def _live_value_and_ttl(
    row: tuple[dict[str, Any], datetime | None] | None,
) -> tuple[dict[str, Any] | None, float | None]:
    """Shared "is this row expired" logic for the single and bulk read paths.

    `row` is `None` when the key doesn't exist, otherwise a plain
    `(value, expires_at)` pair — callers normalize SQLAlchemy `Row` objects
    into that shape before calling this.
    """

    if row is None:
        return None, None
    value, expires_at = row
    if expires_at is None:
        return dict(value), None
    remaining = (expires_at - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        return None, None
    return dict(value), remaining
