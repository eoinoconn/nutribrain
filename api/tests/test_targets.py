"""Tests for T-025 / EC-07: targets domain (set_target, get_effective_target).

Covers:
- no-target: get_effective_target returns None when no target row exists
- multiple-targets-same-day: latest created_at wins; set_target reports overlap
- no completed workouts / no override: falls back to base_calories alone
  (calories_out is None)
- a completed planned_workout with actual_calories=0: a genuine "worked out,
  reported zero calories" day, distinct from no completed workouts at all
- a completed planned_workout's actual_calories feeds calories_out
- a manual override in intervals_calories_out still wins over the
  planned_workouts sum (EC-07, "Reconciling calories-out")
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import (
    IntervalsCaloriesOut,
    IntervalsSource,
    PlannedWorkout,
    PlannedWorkoutSource,
    PlannedWorkoutStatus,
    Target,
)
from app.domain.targets import get_effective_target, set_target


def _clear_targets(session: Session) -> None:
    """Delete any pre-existing Target rows, scoped to this test's own
    transaction (rolled back on teardown — never a permanent write).

    A versioned target with no successor applies to every future day
    (``effective_from <= day`` has no upper bound), so a "no target set"
    assertion is only meaningful against a table this test controls.
    """

    session.execute(delete(Target))
    session.flush()


def _completed_workout(
    *,
    external_id: str,
    local_date: date,
    actual_calories: int,
) -> PlannedWorkout:
    """A minimal completed planned_workouts row for calories_out fixtures."""

    start_at = datetime(local_date.year, local_date.month, local_date.day, 6, 0, tzinfo=UTC)
    return PlannedWorkout(
        external_id=external_id,
        source=PlannedWorkoutSource.intervals_completed,
        local_date=local_date,
        start_at=start_at,
        duration_minutes=45,
        sport_type="Ride",
        icu_joules=None,
        estimated_calories=None,
        actual_calories=actual_calories,
        status=PlannedWorkoutStatus.completed,
        fetched_at=start_at,
    )


class TestGetEffectiveTargetNoTarget:
    """When no target exists, get_effective_target returns None."""

    def test_no_target_returns_none(self, db_session: Session) -> None:
        _clear_targets(db_session)
        result = get_effective_target(db_session, day=date(2031, 7, 26))
        assert result is None

    def test_target_in_future_returns_none(self, db_session: Session, make_target) -> None:
        """A target with effective_from after the query day is not visible."""
        _clear_targets(db_session)
        make_target(effective_from=date(2031, 8, 1))
        result = get_effective_target(db_session, day=date(2031, 7, 26))
        assert result is None


class TestGetEffectiveTargetNoCompletedWorkouts:
    """When a target exists but no completed workout/override, falls back to base alone."""

    def test_missing_calories_out_returns_base_only(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=2000)
        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.base_calories == 2000
        assert result.calories_out is None
        assert result.effective_calories == 2000

    def test_effective_from_propagated(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2031, 3, 15), protein_g=160, carbs_g=250, fat_g=80)
        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.effective_from == date(2031, 3, 15)
        assert result.protein_g == 160
        assert result.carbs_g == 250
        assert result.fat_g == 80


class TestGetEffectiveTargetCompletedZero:
    """A completed workout reporting 0 calories is a genuine result — distinct
    from no completed workout at all."""

    def test_completed_zero_calories_out(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=2000)

        db_session.add(
            _completed_workout(
                external_id="w-zero", local_date=date(2031, 7, 26), actual_calories=0
            )
        )
        db_session.flush()

        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.calories_out == 0
        assert result.effective_calories == 2000  # base + 0


class TestGetEffectiveTargetWithActivity:
    """When a completed workout exists, effective_calories = base + calories_out."""

    def test_activity_added_to_base(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=2000)

        db_session.add(
            _completed_workout(
                external_id="w-500", local_date=date(2031, 7, 26), actual_calories=500
            )
        )
        db_session.flush()

        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.base_calories == 2000
        assert result.calories_out == 500
        assert result.effective_calories == 2500

    def test_multiple_completed_workouts_same_day_are_summed(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=2000)

        db_session.add_all(
            [
                _completed_workout(
                    external_id="w-am", local_date=date(2031, 7, 26), actual_calories=300
                ),
                _completed_workout(
                    external_id="w-pm", local_date=date(2031, 7, 26), actual_calories=200
                ),
            ]
        )
        db_session.flush()

        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.calories_out == 500
        assert result.effective_calories == 2500

    def test_planned_only_workout_does_not_count(self, db_session: Session, make_target) -> None:
        """A status='planned' row (not yet completed) never contributes to calories_out."""

        make_target(effective_from=date(2031, 1, 1), base_calories=2000)

        db_session.add(
            PlannedWorkout(
                external_id="w-planned",
                source=PlannedWorkoutSource.intervals_planned,
                local_date=date(2031, 7, 26),
                start_at=datetime(2031, 7, 26, 6, 0, tzinfo=UTC),
                duration_minutes=60,
                sport_type="Run",
                icu_joules=900000,
                estimated_calories=990,
                actual_calories=None,
                status=PlannedWorkoutStatus.planned,
                fetched_at=datetime(2031, 7, 26, 6, 0, tzinfo=UTC),
            )
        )
        db_session.flush()

        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.calories_out is None
        assert result.effective_calories == 2000


class TestGetEffectiveTargetManualOverrideWins:
    """A manual override in intervals_calories_out still wins over the
    planned_workouts sum (EC-07, "Reconciling calories-out")."""

    def test_manual_override_wins_over_completed_workouts(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=2000)

        db_session.add(
            _completed_workout(
                external_id="w-synced", local_date=date(2031, 7, 26), actual_calories=500
            )
        )
        db_session.add(
            IntervalsCaloriesOut(
                date=date(2031, 7, 26),
                calories_out=700,
                fetched_at=datetime(2031, 7, 26, 8, 0, tzinfo=UTC),
                source=IntervalsSource.manual,
            )
        )
        db_session.flush()

        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.calories_out == 700
        assert result.effective_calories == 2700

    def test_manual_override_wins_even_with_no_completed_workouts(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=2000)

        db_session.add(
            IntervalsCaloriesOut(
                date=date(2031, 7, 26),
                calories_out=0,
                fetched_at=datetime(2031, 7, 26, 8, 0, tzinfo=UTC),
                source=IntervalsSource.manual,
            )
        )
        db_session.flush()

        result = get_effective_target(db_session, day=date(2031, 7, 26))

        assert result is not None
        assert result.calories_out == 0
        assert result.effective_calories == 2000


class TestGetEffectiveTargetMultipleTargets:
    """Multiple targets: the latest effective_from <= day wins."""

    def test_picks_most_recent_effective_from(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=1800)
        make_target(effective_from=date(2031, 6, 1), base_calories=2200)

        result = get_effective_target(db_session, day=date(2031, 7, 26))
        assert result is not None
        assert result.base_calories == 2200
        assert result.effective_from == date(2031, 6, 1)

    def test_multiple_same_day_latest_created_wins(self, db_session: Session) -> None:
        """When two targets share effective_from, the most recently created wins."""
        # Insert first target
        t1 = Target(
            effective_from=date(2031, 7, 1),
            base_calories=2000,
            protein_g=150,
            carbs_g=220,
            fat_g=70,
        )
        db_session.add(t1)
        db_session.flush()

        # Insert second target with same effective_from (later created_at)
        t2 = Target(
            effective_from=date(2031, 7, 1),
            base_calories=2500,
            protein_g=180,
            carbs_g=260,
            fat_g=85,
        )
        db_session.add(t2)
        db_session.flush()

        result = get_effective_target(db_session, day=date(2031, 7, 26))
        assert result is not None
        # The second target (2500) should win because it was created later
        assert result.base_calories == 2500


class TestSetTarget:
    """set_target always inserts a new row, never mutates."""

    def test_creates_new_target(self, db_session: Session) -> None:
        result = set_target(
            db_session,
            base_calories=2200,
            protein_g=150,
            carbs_g=220,
            fat_g=70,
            effective_from=date(2031, 7, 1),
        )

        assert result.id is not None
        assert result.base_calories == 2200
        assert result.protein_g == 150
        assert result.carbs_g == 220
        assert result.fat_g == 70
        assert result.effective_from == date(2031, 7, 1)
        assert result.same_day_overlap is False

    def test_same_day_overlap_reported(self, db_session: Session, make_target) -> None:
        """set_target reports when a target already exists for the same day."""
        make_target(effective_from=date(2031, 7, 1), base_calories=2000)

        result = set_target(
            db_session,
            base_calories=2500,
            protein_g=180,
            carbs_g=260,
            fat_g=85,
            effective_from=date(2031, 7, 1),
        )

        assert result.same_day_overlap is True
        assert result.base_calories == 2500

    def test_never_mutates_existing(self, db_session: Session, make_target) -> None:
        """Inserting a new target with the same date does not modify the old one."""
        original = make_target(effective_from=date(2031, 7, 1), base_calories=2000)
        original_id = original.id

        set_target(
            db_session,
            base_calories=2500,
            protein_g=180,
            carbs_g=260,
            fat_g=85,
            effective_from=date(2031, 7, 1),
        )

        # Original is unchanged
        db_session.expire(original)
        reloaded = db_session.get(Target, original_id)
        assert reloaded is not None
        assert reloaded.base_calories == 2000
