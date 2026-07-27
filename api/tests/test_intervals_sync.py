"""Tests for T-061 (sync worker) and T-045 (status + manual override).

Covers the missing-data rules from §8:
- null from the client writes no row
- 0 from the client writes a genuine zero
- a partial failure on one day still syncs the rest of the range
- a later sync overwrites a manual override and resets source to sync

Also covers the sync status singleton and the manual calories-out override.
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
        return sync_intervals(
            db_session,
            status_session_factory=lambda: nullcontext(db_session),
            **kwargs,
        )

    return _run


class TestSyncIntervalsMissingDataRules:
    def test_null_day_writes_no_row(self, db_session: Session, sync) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {date(2026, 7, 20): None, date(2026, 7, 21): 500, date(2026, 7, 22): None}

        result = sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 1
        assert _cache_row(db_session, date(2026, 7, 20)) is None
        assert _cache_row(db_session, date(2026, 7, 22)) is None

    def test_zero_day_writes_a_genuine_zero(self, db_session: Session, sync) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {date(2026, 7, 20): 0, date(2026, 7, 21): 300, date(2026, 7, 22): None}

        result = sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 2
        row = _cache_row(db_session, date(2026, 7, 20))
        assert row is not None
        assert row.calories_out == 0
        assert row.source == IntervalsSource.sync
        assert row.fetched_at == _NOW

    def test_day_absent_from_fetch_result_writes_no_row(self, db_session: Session, sync) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {date(2026, 7, 21): 400}

        result = sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 1
        assert _cache_row(db_session, date(2026, 7, 20)) is None
        assert _cache_row(db_session, date(2026, 7, 22)) is None


class TestSyncIntervalsPartialFailure:
    def test_one_bad_day_does_not_block_the_rest(self, db_session: Session, sync) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {
                date(2026, 7, 20): 100,
                date(2026, 7, 21): "not-a-number",  # type: ignore[dict-item]
                date(2026, 7, 22): 300,
            }

        result = sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 2
        assert len(result.failures) == 1
        assert result.failures[0]["date"] == "2026-07-21"
        assert _cache_row(db_session, date(2026, 7, 20)) is not None
        assert _cache_row(db_session, date(2026, 7, 21)) is None
        assert _cache_row(db_session, date(2026, 7, 22)) is not None

    def test_upstream_fetch_failure_propagates(self, db_session: Session, sync) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        with pytest.raises(IntervalsUnavailableError):
            sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)


class TestSyncIntervalsManualOverride:
    def test_later_sync_replaces_manual_override(self, db_session: Session, sync) -> None:
        manual_day = date(2026, 7, 21)
        db_session.add(
            IntervalsCaloriesOut(
                date=manual_day,
                calories_out=999,
                fetched_at=datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
                source=IntervalsSource.manual,
            )
        )
        db_session.flush()

        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {manual_day: 450}

        result = sync(from_date=manual_day, to_date=manual_day, now=_NOW, fetch=fetch)

        assert result.days_synced == 1
        row = _cache_row(db_session, manual_day)
        assert row is not None
        assert row.calories_out == 450
        assert row.source == IntervalsSource.sync
        assert row.fetched_at == _NOW


class TestSyncStatus:
    def test_never_synced_returns_all_none(self, db_session: Session) -> None:
        status = get_sync_status(db_session)
        assert status.last_synced_at is None
        assert status.last_error is None

    def test_successful_sync_records_last_synced_at_and_clears_error(
        self, db_session: Session, sync
    ) -> None:
        def failing_fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        with pytest.raises(IntervalsUnavailableError):
            sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch=failing_fetch)

        status = get_sync_status(db_session)
        assert status.last_error == "intervals.icu sync failed."

        def ok_fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {date(2026, 7, 21): 300}

        later = datetime(2026, 7, 26, 13, 0, tzinfo=UTC)
        sync(from_date=_FROM, to_date=_TO, now=later, fetch=ok_fetch)

        status = get_sync_status(db_session)
        assert status.last_synced_at == later
        assert status.last_error is None

    def test_upstream_failure_records_last_error(self, db_session: Session, sync) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            raise IntervalsUnavailableError("intervals.icu sync failed with status 401.")

        with pytest.raises(IntervalsUnavailableError):
            sync(from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

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

    def test_overwrites_an_existing_synced_row(self, db_session: Session) -> None:
        day = date(2026, 7, 23)
        db_session.add(
            IntervalsCaloriesOut(
                date=day,
                calories_out=100,
                fetched_at=datetime(2026, 7, 22, 6, 0, tzinfo=UTC),
                source=IntervalsSource.sync,
            )
        )
        db_session.flush()

        set_manual_calories_out(db_session, day=day, calories_out=750, now=_NOW)

        row = _cache_row(db_session, day)
        assert row is not None
        assert row.calories_out == 750
        assert row.source == IntervalsSource.manual
