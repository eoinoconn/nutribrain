"""Tests for T-061 (sync worker) and T-045 (status + manual override).

EC-07 retired the old ``fetch_activity_calories_by_day`` daily-sum sync path:
``sync_intervals`` now only upserts ``planned_workouts`` (via
``fetch_activities``/``fetch_planned``), and ``calories_out`` is derived from
those rows at read time by ``targets.get_effective_target`` (see
``test_targets.py``). This file now covers:
- a partial failure on one planned-workout row still syncs the rest
- upstream fetch failure propagates and records sync status
- the sync status singleton
- the manual calories-out override write path (``intervals_calories_out``
  is now written *only* by this path, never by a sync)
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import IntervalsCaloriesOut, IntervalsSource
from app.domain.errors import IntervalsUnavailableError
from app.domain.intervals_sync import get_sync_status, set_manual_calories_out, sync_intervals
from app.intervals.client import ActivityDetail, PlannedEventDetail

_FROM = date(2026, 7, 20)
_TO = date(2026, 7, 22)
_NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _cache_row(db_session: Session, day: date) -> IntervalsCaloriesOut | None:
    return db_session.scalar(select(IntervalsCaloriesOut).where(IntervalsCaloriesOut.date == day))


@pytest.fixture
def sync(db_session: Session):
    """``sync_intervals`` bound to ``db_session`` for both data and status writes.

    The real status path deliberately commits on its own connection (so an
    upstream-failure status survives the caller's transaction rolling back —
    see ``intervals_sync._record_sync_failure``). In tests that would write
    permanently to the shared database outside the per-test rollback, so we
    pin status writes to the same ``db_session`` instead.
    """

    def _run(**kwargs):
        kwargs.setdefault("fetch_activities", lambda *, oldest, newest: [])
        kwargs.setdefault("fetch_planned", lambda *, oldest, newest: [])
        return sync_intervals(
            db_session,
            status_session_factory=lambda: nullcontext(db_session),
            **kwargs,
        )

    return _run


class TestSyncIntervalsPartialFailure:
    def test_one_bad_activity_does_not_block_the_rest(self, db_session: Session, sync) -> None:
        good = ActivityDetail(
            external_id="a-good",
            start_date_local="2026-07-20T06:00:00",
            duration_minutes=45.0,
            sport_type="Ride",
            calories=300,
        )
        # A missing start date fails row parsing/validation inside the upsert.
        bad = ActivityDetail(
            external_id="a-bad",
            start_date_local="not-a-date",
            duration_minutes=45.0,
            sport_type="Ride",
            calories=100,
        )

        def fetch_activities(*, oldest: date, newest: date) -> list[ActivityDetail]:
            return [good, bad]

        result = sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch_activities=fetch_activities)

        assert result.days_synced == 1
        assert len(result.failures) == 1
        assert result.failures[0]["external_id"] == "a-bad"

    def test_upstream_fetch_failure_propagates(self, db_session: Session, sync) -> None:
        def fetch_activities(*, oldest: date, newest: date) -> list[ActivityDetail]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        with pytest.raises(IntervalsUnavailableError):
            sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch_activities=fetch_activities)


class TestSyncStatus:
    def test_never_synced_returns_all_none(self, db_session: Session) -> None:
        status = get_sync_status(db_session)
        assert status.last_synced_at is None
        assert status.last_error is None

    def test_successful_sync_records_last_synced_at_and_clears_error(
        self, db_session: Session, sync
    ) -> None:
        def failing_fetch_planned(*, oldest: date, newest: date) -> list[PlannedEventDetail]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        with pytest.raises(IntervalsUnavailableError):
            sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch_planned=failing_fetch_planned)

        status = get_sync_status(db_session)
        assert status.last_error == "intervals.icu sync failed."

        def ok_fetch_planned(*, oldest: date, newest: date) -> list[PlannedEventDetail]:
            return [
                PlannedEventDetail(
                    external_id="e1",
                    start_date_local="2026-07-21T06:00:00",
                    duration_minutes=60.0,
                    sport_type="Run",
                    icu_joules=None,
                )
            ]

        later = datetime(2026, 7, 26, 13, 0, tzinfo=UTC)
        sync(from_date=_FROM, to_date=_TO, now=later, fetch_planned=ok_fetch_planned)

        status = get_sync_status(db_session)
        assert status.last_synced_at == later
        assert status.last_error is None

    def test_upstream_failure_records_last_error(self, db_session: Session, sync) -> None:
        def fetch_activities(*, oldest: date, newest: date) -> list[ActivityDetail]:
            raise IntervalsUnavailableError("intervals.icu sync failed with status 401.")

        with pytest.raises(IntervalsUnavailableError):
            sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch_activities=fetch_activities)

        status = get_sync_status(db_session)
        assert status.last_synced_at is None
        assert status.last_error == "intervals.icu sync failed with status 401."


class TestSetManualCaloriesOut:
    def test_writes_source_manual(self, db_session: Session) -> None:
        day = date(2026, 7, 23)
        result = set_manual_calories_out(db_session, day=day, calories_out=600, now=_NOW)

        assert result.calories_out == 600
        row = _cache_row(db_session, day)
        assert row is not None
        assert row.source == IntervalsSource.manual
        assert row.calories_out == 600
        assert row.fetched_at == _NOW

    def test_overwrites_an_existing_manual_row(self, db_session: Session) -> None:
        day = date(2026, 7, 23)
        db_session.add(
            IntervalsCaloriesOut(
                date=day,
                calories_out=100,
                fetched_at=datetime(2026, 7, 22, 6, 0, tzinfo=UTC),
                source=IntervalsSource.manual,
            )
        )
        db_session.flush()

        set_manual_calories_out(db_session, day=day, calories_out=750, now=_NOW)

        row = _cache_row(db_session, day)
        assert row is not None
        assert row.calories_out == 750
        assert row.source == IntervalsSource.manual
