"""Tests for EC-03: syncing planned_workouts from intervals.icu.

Covers the "Done when" scenarios from the task brief:
- a re-sync upserts rather than duplicates
- a previously-planned row flips to status='completed' with actual_calories
  set once intervals.icu reports the matching external_id as a completed
  activity (the planned -> completed correlation resolved by external_id
  matching across sources -- see sync_planned_workouts's docstring)
- a planned event with no icu_joules gets estimated_calories=None
- a planned event with icu_joules present gets round(icu_joules/1000*1.1)

Also covers wiring: sync_intervals (the shared entrypoint for cron, the
manual sync route, and the MCP tool) also upserts planned_workouts.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import PlannedWorkout, PlannedWorkoutSource, PlannedWorkoutStatus
from app.domain.energy_balance import estimate_workout_calories
from app.domain.intervals_sync import sync_intervals
from app.domain.planned_workouts import sync_planned_workouts
from app.intervals.client import ActivityDetail, PlannedEventDetail

_FROM = date(2026, 8, 1)
_TO = date(2026, 8, 5)
_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _row(
    db_session: Session, *, source: PlannedWorkoutSource, external_id: str
) -> PlannedWorkout | None:
    return db_session.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.source == source, PlannedWorkout.external_id == external_id
        )
    )


def _all_rows(db_session: Session) -> list[PlannedWorkout]:
    return list(db_session.scalars(select(PlannedWorkout)))


class TestEstimateWorkoutCalories:
    def test_flat_conversion(self) -> None:
        assert estimate_workout_calories(2100000) == round(2100000 / 1000 * 1.1)
        assert estimate_workout_calories(2100000) == 2310


class TestSyncPlannedWorkoutsUpsert:
    def test_resync_upserts_rather_than_duplicates(self, db_session: Session) -> None:
        event = PlannedEventDetail(
            external_id="e1",
            start_date_local="2026-08-05T06:00:00",
            duration_minutes=90.0,
            sport_type="Ride",
            icu_joules=2100000.0,
        )

        def fetch_planned(*, oldest: date, newest: date) -> list[PlannedEventDetail]:
            return [event]

        def fetch_activities(*, oldest: date, newest: date) -> list[ActivityDetail]:
            return []

        for _ in range(2):
            sync_planned_workouts(
                db_session,
                from_date=_FROM,
                to_date=_TO,
                now=_NOW,
                fetch_activities=fetch_activities,
                fetch_planned=fetch_planned,
            )

        assert len(_all_rows(db_session)) == 1
        row = _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="e1")
        assert row is not None
        assert row.icu_joules == 2100000
        assert row.estimated_calories == 2310
        assert row.duration_minutes == 90
        assert row.status == PlannedWorkoutStatus.planned

    def test_planned_event_with_icu_joules_gets_estimated_calories(
        self, db_session: Session
    ) -> None:
        event = PlannedEventDetail(
            external_id="e-structured",
            start_date_local="2026-08-03T07:00:00",
            duration_minutes=60.0,
            sport_type="Run",
            icu_joules=1000000.0,
        )

        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [event],
        )

        row = _row(
            db_session, source=PlannedWorkoutSource.intervals_planned, external_id="e-structured"
        )
        assert row is not None
        assert row.icu_joules == 1000000
        assert row.estimated_calories == round(1000000 / 1000 * 1.1)
        assert row.estimated_calories == 1100

    def test_planned_event_without_icu_joules_gets_null_estimate(self, db_session: Session) -> None:
        event = PlannedEventDetail(
            external_id="e-placeholder",
            start_date_local="2026-08-03T07:00:00",
            duration_minutes=45.0,
            sport_type="Run",
            icu_joules=None,
        )

        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [event],
        )

        row = _row(
            db_session, source=PlannedWorkoutSource.intervals_planned, external_id="e-placeholder"
        )
        assert row is not None
        assert row.icu_joules is None
        assert row.estimated_calories is None
        assert row.status == PlannedWorkoutStatus.planned

    def test_completed_activity_upserts_status_completed_with_actual_calories(
        self, db_session: Session
    ) -> None:
        activity = ActivityDetail(
            external_id="a1",
            start_date_local="2026-08-02T06:00:00",
            duration_minutes=55.0,
            sport_type="Ride",
            calories=712,
        )

        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [activity],
            fetch_planned=lambda *, oldest, newest: [],
        )

        row = _row(db_session, source=PlannedWorkoutSource.intervals_completed, external_id="a1")
        assert row is not None
        assert row.status == PlannedWorkoutStatus.completed
        assert row.actual_calories == 712
        assert row.icu_joules is None
        assert row.estimated_calories is None


class TestPlannedToCompletedFlip:
    """The trickiest judgment call: does a planned row flip in place?"""

    def test_previously_planned_row_flips_to_completed(self, db_session: Session) -> None:
        event = PlannedEventDetail(
            external_id="shared-1",
            start_date_local="2026-08-04T06:00:00",
            duration_minutes=90.0,
            sport_type="Ride",
            icu_joules=1800000.0,
        )
        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [event],
        )
        planned_row = _row(
            db_session, source=PlannedWorkoutSource.intervals_planned, external_id="shared-1"
        )
        assert planned_row is not None
        planned_id = planned_row.id

        activity = ActivityDetail(
            external_id="shared-1",
            start_date_local="2026-08-04T06:05:00",
            duration_minutes=88.0,
            sport_type="Ride",
            calories=980,
        )
        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [activity],
            fetch_planned=lambda *, oldest, newest: [],
        )

        # No stale planned duplicate left behind -- exactly one row for this
        # external_id, now flipped in place to the completed source/status.
        assert len(_all_rows(db_session)) == 1
        completed_row = _row(
            db_session, source=PlannedWorkoutSource.intervals_completed, external_id="shared-1"
        )
        assert completed_row is not None
        assert completed_row.id == planned_id
        assert completed_row.status == PlannedWorkoutStatus.completed
        assert completed_row.actual_calories == 980
        assert completed_row.icu_joules is None
        assert completed_row.estimated_calories is None
        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="shared-1")
            is None
        )

    def test_stale_planned_resync_does_not_downgrade_a_completed_row(
        self, db_session: Session
    ) -> None:
        activity = ActivityDetail(
            external_id="shared-2",
            start_date_local="2026-08-04T06:00:00",
            duration_minutes=60.0,
            sport_type="Run",
            calories=500,
        )
        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [activity],
            fetch_planned=lambda *, oldest, newest: [],
        )

        # Upstream /events still (or again) returns the same id -- e.g. a
        # stale calendar entry that hasn't dropped off yet.
        event = PlannedEventDetail(
            external_id="shared-2",
            start_date_local="2026-08-04T06:00:00",
            duration_minutes=60.0,
            sport_type="Run",
            icu_joules=900000.0,
        )
        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [event],
        )

        assert len(_all_rows(db_session)) == 1
        completed_row = _row(
            db_session, source=PlannedWorkoutSource.intervals_completed, external_id="shared-2"
        )
        assert completed_row is not None
        assert completed_row.status == PlannedWorkoutStatus.completed
        assert completed_row.actual_calories == 500
        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="shared-2")
            is None
        )


class TestSyncIntervalsWiresPlannedWorkouts:
    def test_sync_intervals_also_upserts_planned_workouts(self, db_session: Session) -> None:
        event = PlannedEventDetail(
            external_id="wired-1",
            start_date_local="2026-08-02T06:00:00",
            duration_minutes=30.0,
            sport_type="Swim",
            icu_joules=300000.0,
        )
        activity = ActivityDetail(
            external_id="wired-2",
            start_date_local="2026-08-01T06:00:00",
            duration_minutes=40.0,
            sport_type="Run",
            calories=350,
        )

        result = sync_intervals(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [activity],
            fetch_planned=lambda *, oldest, newest: [event],
            status_session_factory=lambda: nullcontext(db_session),
        )

        # EC-07: days_synced now counts planned_workouts rows upserted
        # (the old calories-out daily-sum path this field used to count is
        # retired).
        assert result.days_synced == 2
        planned = _row(
            db_session, source=PlannedWorkoutSource.intervals_planned, external_id="wired-1"
        )
        completed = _row(
            db_session, source=PlannedWorkoutSource.intervals_completed, external_id="wired-2"
        )
        assert planned is not None
        assert planned.estimated_calories == round(300000 / 1000 * 1.1)
        assert completed is not None
        assert completed.actual_calories == 350

    def test_upstream_planned_workouts_fetch_failure_propagates_and_records_status(
        self, db_session: Session
    ) -> None:
        from app.domain.errors import IntervalsUnavailableError
        from app.domain.intervals_sync import get_sync_status

        def failing_fetch_planned(*, oldest: date, newest: date) -> list[PlannedEventDetail]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        with pytest.raises(IntervalsUnavailableError):
            sync_intervals(
                db_session,
                from_date=_FROM,
                to_date=_TO,
                now=_NOW,
                fetch_activities=lambda *, oldest, newest: [],
                fetch_planned=failing_fetch_planned,
                status_session_factory=lambda: nullcontext(db_session),
            )

        status = get_sync_status(db_session)
        assert status.last_error == "intervals.icu sync failed."
