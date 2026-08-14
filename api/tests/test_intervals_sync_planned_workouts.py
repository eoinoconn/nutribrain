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

# A far-future, distinctive range: this suite runs against a shared dev
# Neon database (see api/.env), not an ephemeral one per run, and real
# synced planned_workouts rows already exist around the actual current
# date (confirmed: a real `intervals_planned` row for today collided with
# this range when it was 2026-08-01..05, making count-based assertions
# here wrong -- each test's own transaction still rolled back cleanly, so
# nothing was permanently lost, but the *assertions* saw real rows
# alongside the test's own). Matches the convention `test_energy_balance.py`
# already uses for the same reason.
_FROM = date(2031, 8, 1)
_TO = date(2031, 8, 5)
_NOW = datetime(2031, 8, 5, 12, 0, tzinfo=UTC)


def _row(
    db_session: Session, *, source: PlannedWorkoutSource, external_id: str
) -> PlannedWorkout | None:
    return db_session.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.source == source, PlannedWorkout.external_id == external_id
        )
    )


def _all_rows(db_session: Session) -> list[PlannedWorkout]:
    """Rows within this suite's own [_FROM, _TO] range only -- an unscoped
    `select(PlannedWorkout)` counts every row in the shared dev DB,
    including real committed rows around the actual current date (see the
    `_FROM`/`_TO` comment above for why that's a real, confirmed collision).
    """

    return list(
        db_session.scalars(
            select(PlannedWorkout).where(
                PlannedWorkout.local_date >= _FROM, PlannedWorkout.local_date <= _TO
            )
        )
    )


class TestEstimateWorkoutCalories:
    def test_flat_conversion(self) -> None:
        assert estimate_workout_calories(2100000) == round(2100000 / 1000 * 1.1)
        assert estimate_workout_calories(2100000) == 2310


class TestSyncPlannedWorkoutsUpsert:
    def test_resync_upserts_rather_than_duplicates(self, db_session: Session) -> None:
        event = PlannedEventDetail(
            external_id="e1",
            start_date_local="2031-08-05T06:00:00",
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
            start_date_local="2031-08-03T07:00:00",
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
            start_date_local="2031-08-03T07:00:00",
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
            start_date_local="2031-08-02T06:00:00",
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
        # Real intervals.icu behavior (confirmed via the vendored OpenAPI
        # spec, not a shared id): an event and its resulting activity have
        # *different* ids. The activity carries the event's id separately,
        # in paired_event_id.
        event = PlannedEventDetail(
            external_id="event-1",
            start_date_local="2031-08-04T06:00:00",
            duration_minutes=90.0,
            sport_type="Ride",
            icu_joules=1800000.0,
        )
        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=datetime(2031, 8, 3, 12, 0, tzinfo=UTC),
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [event],
        )
        planned_row = _row(
            db_session, source=PlannedWorkoutSource.intervals_planned, external_id="event-1"
        )
        assert planned_row is not None
        planned_id = planned_row.id

        activity = ActivityDetail(
            external_id="activity-1",
            start_date_local="2031-08-04T06:05:00",
            duration_minutes=88.0,
            sport_type="Ride",
            calories=980,
            paired_event_id="event-1",
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
        # workout, now flipped in place to the completed source/status,
        # identified by the activity's own id (not the original event's).
        assert len(_all_rows(db_session)) == 1
        completed_row = _row(
            db_session, source=PlannedWorkoutSource.intervals_completed, external_id="activity-1"
        )
        assert completed_row is not None
        assert completed_row.id == planned_id
        assert completed_row.paired_event_id == "event-1"
        assert completed_row.status == PlannedWorkoutStatus.completed
        assert completed_row.actual_calories == 980
        assert completed_row.icu_joules is None
        assert completed_row.estimated_calories is None
        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="event-1")
            is None
        )

    def test_consolidates_a_pre_existing_duplicate_pair_onto_the_completed_row(
        self, db_session: Session
    ) -> None:
        """A real scenario hit while shipping this fix: an activity had
        already been synced once under the old (incorrect) same-external_id
        guess, before paired_event_id-based correlation existed -- so it got
        its own row with no flip, leaving the original planned row
        stranded. The next sync now correctly finds the planned row via
        paired_event_id, but naively flipping it would collide with the
        already-existing completed row's (source, external_id) key. Both
        must consolidate onto one row instead of erroring.
        """

        planned_leftover = PlannedWorkout(
            external_id="event-4",
            source=PlannedWorkoutSource.intervals_planned,
            local_date=date(2031, 8, 4),
            start_at=datetime(2031, 8, 4, 6, 0, tzinfo=UTC),
            duration_minutes=54,
            sport_type="Swim",
            icu_joules=None,
            estimated_calories=None,
            actual_calories=None,
            status=PlannedWorkoutStatus.planned,
            fetched_at=_NOW,
        )
        completed_leftover = PlannedWorkout(
            external_id="activity-4",
            source=PlannedWorkoutSource.intervals_completed,
            local_date=date(2031, 8, 4),
            start_at=datetime(2031, 8, 4, 6, 5, tzinfo=UTC),
            duration_minutes=40,
            sport_type="Swim",
            icu_joules=None,
            estimated_calories=None,
            actual_calories=466,
            status=PlannedWorkoutStatus.completed,
            fetched_at=_NOW,
            # No paired_event_id yet -- this row predates the fix, exactly
            # like the real leftover row this test models.
            paired_event_id=None,
        )
        db_session.add_all([planned_leftover, completed_leftover])
        db_session.flush()
        completed_id = completed_leftover.id

        activity = ActivityDetail(
            external_id="activity-4",
            start_date_local="2031-08-04T06:05:00",
            duration_minutes=40.0,
            sport_type="Swim",
            calories=466,
            paired_event_id="event-4",
        )
        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [activity],
            fetch_planned=lambda *, oldest, newest: [],
        )

        assert len(_all_rows(db_session)) == 1
        row = _row(
            db_session, source=PlannedWorkoutSource.intervals_completed, external_id="activity-4"
        )
        assert row is not None
        assert row.id == completed_id
        assert row.paired_event_id == "event-4"
        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="event-4")
            is None
        )

    def test_activity_and_its_still_cached_event_in_the_same_sync_produce_one_row(
        self, db_session: Session
    ) -> None:
        """The reported real-world bug: a single sync call whose /activities
        response already includes the completed workout while /events still
        (also) returns its original calendar entry -- intervals.icu doesn't
        drop a completed event from /events immediately. Activities are
        processed first (see sync_planned_workouts), so the activity creates
        a fresh completed row (nothing planned exists yet to flip) carrying
        paired_event_id; the event processed afterward must then recognize
        that id via paired_event_id and skip, rather than creating a second,
        stuck-forever "planned" row for the same real workout.
        """

        activity = ActivityDetail(
            external_id="activity-3",
            start_date_local="2031-08-04T06:00:00",
            duration_minutes=40.0,
            sport_type="Swim",
            calories=466,
            paired_event_id="event-3",
        )
        event = PlannedEventDetail(
            external_id="event-3",
            start_date_local="2031-08-04T00:00:00",
            duration_minutes=54.0,
            sport_type="Swim",
            icu_joules=None,
        )

        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [activity],
            fetch_planned=lambda *, oldest, newest: [event],
        )

        assert len(_all_rows(db_session)) == 1
        completed_row = _row(
            db_session, source=PlannedWorkoutSource.intervals_completed, external_id="activity-3"
        )
        assert completed_row is not None
        assert completed_row.paired_event_id == "event-3"
        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="event-3")
            is None
        )

    def test_stale_planned_resync_does_not_downgrade_a_completed_row(
        self, db_session: Session
    ) -> None:
        activity = ActivityDetail(
            external_id="activity-2",
            start_date_local="2031-08-04T06:00:00",
            duration_minutes=60.0,
            sport_type="Run",
            calories=500,
            paired_event_id="event-2",
        )
        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [activity],
            fetch_planned=lambda *, oldest, newest: [],
        )

        # Upstream /events still (or again) returns the same event -- e.g. a
        # stale calendar entry that hasn't dropped off yet.
        event = PlannedEventDetail(
            external_id="event-2",
            start_date_local="2031-08-04T06:00:00",
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
            db_session, source=PlannedWorkoutSource.intervals_completed, external_id="activity-2"
        )
        assert completed_row is not None
        assert completed_row.status == PlannedWorkoutStatus.completed
        assert completed_row.actual_calories == 500
        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="event-2")
            is None
        )


class TestStalePlannedRemoval:
    """EC-12: a planned row whose event disappears from intervals.icu should
    disappear from the app too, on the next sync covering its date.
    """

    def test_planned_row_removed_when_event_no_longer_returned(self, db_session: Session) -> None:
        event = PlannedEventDetail(
            external_id="vanishing",
            start_date_local="2031-08-03T07:00:00",
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
        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="vanishing")
            is not None
        )

        # Re-sync the same range; intervals.icu no longer returns this event
        # (deleted upstream).
        result = sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [],
        )

        assert (
            _row(db_session, source=PlannedWorkoutSource.intervals_planned, external_id="vanishing")
            is None
        )
        assert result.stale_planned_removed == 1

    def test_manual_row_is_never_removed_by_a_sync(self, db_session: Session) -> None:
        manual = PlannedWorkout(
            external_id=None,
            source=PlannedWorkoutSource.manual,
            local_date=date(2031, 8, 3),
            start_at=datetime(2031, 8, 3, 7, 0, tzinfo=UTC),
            duration_minutes=60,
            sport_type=None,
            icu_joules=None,
            estimated_calories=400,
            actual_calories=None,
            status=PlannedWorkoutStatus.planned,
            fetched_at=_NOW,
        )
        db_session.add(manual)
        db_session.flush()

        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [],
        )

        assert db_session.get(PlannedWorkout, manual.id) is not None

    def test_completed_row_is_never_removed_by_a_sync_with_no_events(
        self, db_session: Session
    ) -> None:
        activity = ActivityDetail(
            external_id="stays-completed",
            start_date_local="2031-08-02T06:00:00",
            duration_minutes=55.0,
            sport_type="Ride",
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

        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [],
        )

        row = _row(
            db_session,
            source=PlannedWorkoutSource.intervals_completed,
            external_id="stays-completed",
        )
        assert row is not None
        assert row.status == PlannedWorkoutStatus.completed

    def test_planned_row_outside_the_synced_range_is_untouched(self, db_session: Session) -> None:
        outside_range = PlannedWorkout(
            external_id="outside",
            source=PlannedWorkoutSource.intervals_planned,
            local_date=date(2031, 9, 1),
            start_at=datetime(2031, 9, 1, 7, 0, tzinfo=UTC),
            duration_minutes=60,
            sport_type="Run",
            icu_joules=1000000,
            estimated_calories=1100,
            actual_calories=None,
            status=PlannedWorkoutStatus.planned,
            fetched_at=_NOW,
        )
        db_session.add(outside_range)
        db_session.flush()

        sync_planned_workouts(
            db_session,
            from_date=_FROM,
            to_date=_TO,
            now=_NOW,
            fetch_activities=lambda *, oldest, newest: [],
            fetch_planned=lambda *, oldest, newest: [],
        )

        assert db_session.get(PlannedWorkout, outside_range.id) is not None


class TestSyncIntervalsWiresPlannedWorkouts:
    def test_sync_intervals_also_upserts_planned_workouts(self, db_session: Session) -> None:
        event = PlannedEventDetail(
            external_id="wired-1",
            start_date_local="2031-08-02T06:00:00",
            duration_minutes=30.0,
            sport_type="Swim",
            icu_joules=300000.0,
        )
        activity = ActivityDetail(
            external_id="wired-2",
            start_date_local="2031-08-01T06:00:00",
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
