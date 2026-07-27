"""Tests for the cron entrypoint (T-062, §8, §10).

Covers the date-range default (last ``INTERVALS_SYNC_DAYS`` days ending
yesterday) and the exit-code contract: 0 on success (including partial
per-day failures), non-zero when the sync fails outright.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.errors import IntervalsUnavailableError
from app.intervals import sync_recent
from tests.conftest import FROZEN_INSTANT


class _FakeResult:
    def __init__(self, from_date: date, to_date: date, *, days_synced: int, failures: list):
        self.from_date = from_date
        self.to_date = to_date
        self.days_synced = days_synced
        self.failures = failures


@pytest.fixture
def session_factory(db_session: Session):
    return lambda: nullcontext(db_session)


class TestMain:
    def test_success_syncs_default_range_and_returns_zero(
        self, session_factory, monkeypatch
    ) -> None:
        captured = {}

        def fake_sync_intervals(session, *, from_date, to_date):
            captured["from_date"] = from_date
            captured["to_date"] = to_date
            return _FakeResult(from_date, to_date, days_synced=2, failures=[])

        monkeypatch.setattr(sync_recent, "sync_intervals", fake_sync_intervals)

        exit_code = sync_recent.main(session_factory=session_factory, now=FROZEN_INSTANT)

        assert exit_code == 0
        expected_to = FROZEN_INSTANT.date() - timedelta(days=1)
        expected_from = expected_to - timedelta(days=sync_recent.settings.intervals_sync_days - 1)
        assert captured["to_date"] == expected_to
        assert captured["from_date"] == expected_from

    def test_partial_day_failures_still_return_zero(self, session_factory, monkeypatch) -> None:
        def fake_sync_intervals(session, *, from_date, to_date):
            return _FakeResult(
                from_date, to_date, days_synced=1, failures=[{"date": "2026-07-20", "error": "x"}]
            )

        monkeypatch.setattr(sync_recent, "sync_intervals", fake_sync_intervals)

        assert sync_recent.main(session_factory=session_factory, now=FROZEN_INSTANT) == 0

    def test_total_failure_returns_nonzero(self, session_factory, monkeypatch) -> None:
        def fake_sync_intervals(session, *, from_date, to_date):
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        monkeypatch.setattr(sync_recent, "sync_intervals", fake_sync_intervals)

        assert sync_recent.main(session_factory=session_factory, now=FROZEN_INSTANT) != 0
