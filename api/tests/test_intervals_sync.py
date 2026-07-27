"""Tests for T-061: intervals sync worker.

Covers the missing-data rules from §8:
- null from the client writes no row
- 0 from the client writes a genuine zero
- a partial failure on one day still syncs the rest of the range
- a later sync overwrites a manual override and resets source to sync
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import IntervalsCaloriesOut, IntervalsSource
from app.domain.errors import IntervalsUnavailableError
from app.domain.intervals_sync import sync_intervals

_FROM = date(2026, 7, 20)
_TO = date(2026, 7, 22)
_NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _cache_row(db_session: Session, day: date) -> IntervalsCaloriesOut | None:
    return db_session.scalar(select(IntervalsCaloriesOut).where(IntervalsCaloriesOut.date == day))


class TestSyncIntervalsMissingDataRules:
    def test_null_day_writes_no_row(self, db_session: Session) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {date(2026, 7, 20): None, date(2026, 7, 21): 500, date(2026, 7, 22): None}

        result = sync_intervals(db_session, from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 1
        assert _cache_row(db_session, date(2026, 7, 20)) is None
        assert _cache_row(db_session, date(2026, 7, 22)) is None

    def test_zero_day_writes_a_genuine_zero(self, db_session: Session) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {date(2026, 7, 20): 0, date(2026, 7, 21): 300, date(2026, 7, 22): None}

        result = sync_intervals(db_session, from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 2
        row = _cache_row(db_session, date(2026, 7, 20))
        assert row is not None
        assert row.calories_out == 0
        assert row.source == IntervalsSource.sync
        assert row.fetched_at == _NOW

    def test_day_absent_from_fetch_result_writes_no_row(self, db_session: Session) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {date(2026, 7, 21): 400}

        result = sync_intervals(db_session, from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 1
        assert _cache_row(db_session, date(2026, 7, 20)) is None
        assert _cache_row(db_session, date(2026, 7, 22)) is None


class TestSyncIntervalsPartialFailure:
    def test_one_bad_day_does_not_block_the_rest(self, db_session: Session) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {
                date(2026, 7, 20): 100,
                date(2026, 7, 21): "not-a-number",  # type: ignore[dict-item]
                date(2026, 7, 22): 300,
            }

        result = sync_intervals(db_session, from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)

        assert result.days_synced == 2
        assert len(result.failures) == 1
        assert result.failures[0]["date"] == "2026-07-21"
        assert _cache_row(db_session, date(2026, 7, 20)) is not None
        assert _cache_row(db_session, date(2026, 7, 21)) is None
        assert _cache_row(db_session, date(2026, 7, 22)) is not None

    def test_upstream_fetch_failure_propagates(self, db_session: Session) -> None:
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        with pytest.raises(IntervalsUnavailableError):
            sync_intervals(db_session, from_date=_FROM, to_date=_TO, now=_NOW, fetch=fetch)


class TestSyncIntervalsManualOverride:
    def test_later_sync_replaces_manual_override(self, db_session: Session) -> None:
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

        result = sync_intervals(
            db_session, from_date=manual_day, to_date=manual_day, now=_NOW, fetch=fetch
        )

        assert result.days_synced == 1
        row = _cache_row(db_session, manual_day)
        assert row is not None
        assert row.calories_out == 450
        assert row.source == IntervalsSource.sync
        assert row.fetched_at == _NOW
