"""Tests for T-053 / EC-07: MCP sync_intervals tool.

The tool is exercised end-to-end via ``mcp.call_tool`` with
``app.mcp.tools_sync.run_with_session`` monkeypatched to run against the
transactional ``db_session`` fixture (real DB, rolled back on teardown)
instead of opening a genuinely-committing ``session_scope()`` — otherwise
every call here would leave real rows in the shared database.

Since EC-07, ``sync_intervals`` only syncs ``planned_workouts`` (via
``fetch_activities``/``fetch_planned``) — the old ``fetch`` (calories-out
daily-sum) parameter is retired, and ``days_synced`` now counts workouts
upserted.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date

import pytest
from sqlalchemy.orm import Session

import app.mcp.tools_sync as tools_sync_module
from app.domain.errors import IntervalsUnavailableError
from app.intervals.client import ActivityDetail, PlannedEventDetail
from app.main import mcp


def _patch_run_with_session(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    *,
    fetch_activities=lambda *, oldest, newest: [],
    fetch_planned=lambda *, oldest, newest: [],
):
    def fake_run_with_session(operation, /, *args, **kwargs):
        return operation(
            db_session,
            *args,
            fetch_activities=fetch_activities,
            fetch_planned=fetch_planned,
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

    def fetch_activities(*, oldest: date, newest: date) -> list[ActivityDetail]:
        seen_range["oldest"] = oldest
        seen_range["newest"] = newest
        return [
            ActivityDetail(
                external_id="a1",
                start_date_local=f"{newest.isoformat()}T06:00:00",
                duration_minutes=30.0,
                sport_type="Run",
                calories=300,
            )
        ]

    _patch_run_with_session(monkeypatch, db_session, fetch_activities=fetch_activities)

    result = await _call_sync_tool(local_tz="UTC")

    assert result.is_error is False
    payload = result.structured_content["result"]
    assert payload["days_synced"] == 1
    assert (seen_range["newest"] - seen_range["oldest"]).days == 6


@pytest.mark.asyncio
async def test_sync_intervals_explicit_range(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    def fetch_activities(*, oldest: date, newest: date) -> list[ActivityDetail]:
        assert oldest == date(2026, 7, 20)
        assert newest == date(2026, 7, 22)
        return [
            ActivityDetail(
                external_id="a1",
                start_date_local="2026-07-20T06:00:00",
                duration_minutes=60.0,
                sport_type="Ride",
                calories=0,
            ),
            ActivityDetail(
                external_id="a2",
                start_date_local="2026-07-22T06:00:00",
                duration_minutes=45.0,
                sport_type="Run",
                calories=400,
            ),
        ]

    _patch_run_with_session(monkeypatch, db_session, fetch_activities=fetch_activities)

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
    def fetch_planned(*, oldest: date, newest: date) -> list[PlannedEventDetail]:
        raise IntervalsUnavailableError("intervals.icu sync failed.")

    _patch_run_with_session(monkeypatch, db_session, fetch_planned=fetch_planned)

    result = await _call_sync_tool(local_tz="UTC", from_date="2026-07-20", to_date="2026-07-22")

    payload = result.structured_content["result"]
    assert payload["error"] == "intervals_unavailable"
