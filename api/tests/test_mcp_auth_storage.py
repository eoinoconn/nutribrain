"""Unit tests for the Postgres-backed `AsyncKeyValue` adapter (F-101).

Exercises exactly the surface `OAuthProxy`/`GoogleProvider` actually calls on
`client_storage` (get/put/delete/ttl, via `PydanticAdapter` — see
`fastmcp/server/auth/oauth_proxy/proxy.py` and
`key_value/aio/adapters/pydantic/base.py`), plus the bulk `_many` variants
required for full `AsyncKeyValue` protocol conformance.

Each test uses a fresh, randomly named collection so tests can run
concurrently/out of order against the shared test database without stepping
on each other, and cleans up its own rows on teardown.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.mcp_auth.storage import PostgresKeyValueStore


@pytest_asyncio.fixture
async def store() -> AsyncIterator[PostgresKeyValueStore]:
    kv = PostgresKeyValueStore()
    try:
        yield kv
    finally:
        await kv.aclose()


def _collection() -> str:
    return f"test-{uuid.uuid4().hex}"


@pytest.mark.asyncio
class TestRoundTrip:
    async def test_put_then_get_returns_the_value(self, store: PostgresKeyValueStore) -> None:
        collection = _collection()

        await store.put("client-1", {"name": "Claude Web"}, collection=collection)

        assert await store.get("client-1", collection=collection) == {"name": "Claude Web"}

    async def test_get_missing_key_returns_none(self, store: PostgresKeyValueStore) -> None:
        assert await store.get("does-not-exist", collection=_collection()) is None

    async def test_put_overwrites_an_existing_key(self, store: PostgresKeyValueStore) -> None:
        collection = _collection()

        await store.put("client-1", {"name": "old"}, collection=collection)
        await store.put("client-1", {"name": "new"}, collection=collection)

        assert await store.get("client-1", collection=collection) == {"name": "new"}

    async def test_delete_removes_the_key_and_reports_it_existed(
        self, store: PostgresKeyValueStore
    ) -> None:
        collection = _collection()
        await store.put("client-1", {"name": "Claude Web"}, collection=collection)

        deleted = await store.delete("client-1", collection=collection)

        assert deleted is True
        assert await store.get("client-1", collection=collection) is None

    async def test_delete_missing_key_returns_false(self, store: PostgresKeyValueStore) -> None:
        assert await store.delete("nope", collection=_collection()) is False


@pytest.mark.asyncio
class TestTtlExpiry:
    async def test_entry_without_ttl_has_no_expiry(self, store: PostgresKeyValueStore) -> None:
        collection = _collection()
        await store.put("code-1", {"code": "abc"}, collection=collection)

        value, ttl = await store.ttl("code-1", collection=collection)

        assert value == {"code": "abc"}
        assert ttl is None

    async def test_entry_within_ttl_is_returned_with_remaining_seconds(
        self, store: PostgresKeyValueStore
    ) -> None:
        collection = _collection()
        await store.put("code-1", {"code": "abc"}, collection=collection, ttl=3600)

        value, ttl = await store.ttl("code-1", collection=collection)

        assert value == {"code": "abc"}
        assert ttl is not None
        assert 0 < ttl <= 3600

    async def test_entry_past_expiry_behaves_as_missing(self, store: PostgresKeyValueStore) -> None:
        collection = _collection()
        # A negative TTL is already in the past the instant it's written.
        await store.put("code-1", {"code": "abc"}, collection=collection, ttl=-1)

        assert await store.get("code-1", collection=collection) is None
        assert await store.ttl("code-1", collection=collection) == (None, None)


@pytest.mark.asyncio
class TestCollectionIsolation:
    async def test_same_key_in_different_collections_does_not_collide(
        self, store: PostgresKeyValueStore
    ) -> None:
        collection_a = _collection()
        collection_b = _collection()

        await store.put("shared-key", {"who": "a"}, collection=collection_a)
        await store.put("shared-key", {"who": "b"}, collection=collection_b)

        assert await store.get("shared-key", collection=collection_a) == {"who": "a"}
        assert await store.get("shared-key", collection=collection_b) == {"who": "b"}

    async def test_deleting_in_one_collection_leaves_the_other_untouched(
        self, store: PostgresKeyValueStore
    ) -> None:
        collection_a = _collection()
        collection_b = _collection()
        await store.put("shared-key", {"who": "a"}, collection=collection_a)
        await store.put("shared-key", {"who": "b"}, collection=collection_b)

        await store.delete("shared-key", collection=collection_a)

        assert await store.get("shared-key", collection=collection_a) is None
        assert await store.get("shared-key", collection=collection_b) == {"who": "b"}

    async def test_default_collection_is_used_when_none_is_given(
        self, store: PostgresKeyValueStore
    ) -> None:
        key = f"default-key-{uuid.uuid4().hex}"
        try:
            await store.put(key, {"n": 1})

            assert await store.get(key) == {"n": 1}
            assert await store.get(key, collection="default") == {"n": 1}
        finally:
            await store.delete(key)


@pytest.mark.asyncio
class TestBulkOperations:
    async def test_put_many_and_get_many_round_trip(self, store: PostgresKeyValueStore) -> None:
        collection = _collection()

        await store.put_many(["a", "b"], [{"v": 1}, {"v": 2}], collection=collection)

        assert await store.get_many(["a", "b", "missing"], collection=collection) == [
            {"v": 1},
            {"v": 2},
            None,
        ]

    async def test_delete_many_returns_count_and_removes_keys(
        self, store: PostgresKeyValueStore
    ) -> None:
        collection = _collection()
        await store.put_many(["a", "b"], [{"v": 1}, {"v": 2}], collection=collection)

        deleted = await store.delete_many(["a", "b", "missing"], collection=collection)

        assert deleted == 2
        assert await store.get_many(["a", "b"], collection=collection) == [None, None]

    async def test_ttl_many_reports_expired_entries_as_missing(
        self, store: PostgresKeyValueStore
    ) -> None:
        collection = _collection()
        await store.put("live", {"v": 1}, collection=collection)
        await store.put("dead", {"v": 2}, collection=collection, ttl=-1)

        results = await store.ttl_many(["live", "dead", "missing"], collection=collection)

        assert results[0][0] == {"v": 1}
        assert results[0][1] is None
        assert results[1] == (None, None)
        assert results[2] == (None, None)
