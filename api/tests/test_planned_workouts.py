"""Tests for EC-04: manual planned-workout domain logic.

Covers:
- happy path: a source='manual' row is inserted with the expected fields,
  local_date derived from start_at in the account's configured timezone
- duration_minutes defaults when omitted, and is honored when supplied
- naive start_at is rejected with NaiveDatetimeError (not a bare ValueError)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db import PlannedWorkout, PlannedWorkoutSource, PlannedWorkoutStatus
from app.domain.errors import NaiveDatetimeError
from app.domain.planned_workouts import DEFAULT_DURATION_MINUTES, create_manual_planned_workout
from app.domain.settings import update_settings


class TestCreateManualPlannedWorkout:
    def test_happy_path_inserts_manual_row(self, db_session: Session) -> None:
        start_at = datetime(2026, 8, 2, 7, 0, tzinfo=UTC)

        result = create_manual_planned_workout(
            db_session,
            start_at=start_at,
            estimated_calories=450,
        )

        assert result.source == PlannedWorkoutSource.manual
        assert result.status == PlannedWorkoutStatus.planned
        assert result.external_id is None
        assert result.sport_type is None
        assert result.icu_joules is None
        assert result.actual_calories is None
        assert result.estimated_calories == 450
        assert result.start_at == start_at
        assert result.local_date == start_at.date()
        assert result.duration_minutes == DEFAULT_DURATION_MINUTES

        row = db_session.get(PlannedWorkout, result.id)
        assert row is not None
        assert row.source == PlannedWorkoutSource.manual
        assert row.local_date == start_at.date()

    def test_local_date_derives_from_account_timezone(self, db_session: Session) -> None:
        update_settings(db_session, local_timezone="Pacific/Auckland")
        # 23:00 UTC on 2026-08-01 is already 2026-08-02 in Pacific/Auckland (+12/+13).
        start_at = datetime(2026, 8, 1, 23, 0, tzinfo=UTC)

        result = create_manual_planned_workout(
            db_session,
            start_at=start_at,
            estimated_calories=300,
        )

        assert result.local_date.isoformat() == "2026-08-02"

    def test_custom_duration_is_honored(self, db_session: Session) -> None:
        start_at = datetime(2026, 8, 2, 7, 0, tzinfo=UTC)

        result = create_manual_planned_workout(
            db_session,
            start_at=start_at,
            estimated_calories=600,
            duration_minutes=90,
        )

        assert result.duration_minutes == 90

    def test_naive_start_at_raises_naive_datetime_error(self, db_session: Session) -> None:
        naive_start_at = datetime(2026, 8, 2, 7, 0)  # noqa: DTZ001 - intentional for this test

        with pytest.raises(NaiveDatetimeError) as exc_info:
            create_manual_planned_workout(
                db_session,
                start_at=naive_start_at,
                estimated_calories=450,
            )

        assert exc_info.value.error == "naive_datetime"
