"""Tests for T-053: MCP sync_intervals tool.

The tool is exercised end-to-end via ``mcp.call_tool`` with
``app.mcp.tools_sync.run_with_session`` monkeypatched to run against the
transactional ``db_session`` fixture (real DB, rolled back on teardown)
instead of opening a genuinely-committing ``session_scope()`` — otherwise
every call here would leave real rows in the shared database.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date

import pytest
from sqlalchemy.orm import Session

import app.mcp.tools_sync as tools_sync_module
from app.domain.errors import IntervalsUnavailableError
from app.main import mcp


def _patch_run_with_session(monkeypatch: pytest.MonkeyPatch, db_session: Session, *, fetch):
    def fake_run_with_session(operation, /, *args, **kwargs):
        return operation(
            db_session,
            *args,
            fetch=fetch,
            status_session_factory=lambda: nullcontext(db_session),
            **kwargs,
        )

    monkeypatch.setattr(tools_sync_module, "run_with_session", fake_run_with_session)


async def _call_sync_tool(
    *, local_tz: str, from_date: str | None = None, to_date: str | None = None
):
    args: dict[str, object] = {"local_tz": local_tz}
    if from_date is not None:
        args["from_date"] = from_date
    if to_date is not None:
        args["to_date"] = to_date
    return await mcp.call_tool("sync_intervals", args)


@pytest.mark.asyncio
async def test_sync_intervals_defaults_to_last_seven_days(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    seen_range: dict[str, date] = {}

    def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
        seen_range["oldest"] = oldest
        seen_range["newest"] = newest
        return {newest: 300}

    _patch_run_with_session(monkeypatch, db_session, fetch=fetch)

    result = await _call_sync_tool(local_tz="UTC")

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["days_synced"] == 1
    assert (seen_range["newest"] - seen_range["oldest"]).days == 6


@pytest.mark.asyncio
async def test_sync_intervals_explicit_range(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
        assert oldest == date(2026, 7, 20)
        assert newest == date(2026, 7, 22)
        return {date(2026, 7, 20): 0, date(2026, 7, 21): None, date(2026, 7, 22): 400}

    _patch_run_with_session(monkeypatch, db_session, fetch=fetch)

    result = await _call_sync_tool(local_tz="UTC", from_date="2026-07-20", to_date="2026-07-22")

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["from_date"] == "2026-07-20"
    assert payload["to_date"] == "2026-07-22"
    assert payload["days_synced"] == 2
    assert payload["failures"] == []


@pytest.mark.asyncio
async def test_sync_intervals_upstream_failure_returns_tool_error(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
        raise IntervalsUnavailableError("intervals.icu sync failed.")

    _patch_run_with_session(monkeypatch, db_session, fetch=fetch)

    result = await _call_sync_tool(local_tz="UTC", from_date="2026-07-20", to_date="2026-07-22")

    payload = result.structured_content["result"]
    assert payload["error"] == "intervals_unavailable"
