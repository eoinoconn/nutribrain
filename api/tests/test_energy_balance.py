"""Tests for EC-05: `compute_energy_timeline` domain function.

Covers every explicit scenario from the task's "Done when" list (§5,
docs/features/energy_balance_chart.md):

- a day with no meals/workouts (flat basal line)
- a day with a past meal and a past workout (correct solid-line steps)
- a day with a future-logged meal and a future-planned workout (correct
  dashed-line steps, not assumed-zero)
- a `planned` row past its 4-hour grace window with no completion (dropped)
- a `planned` row with null `estimated_calories` (excluded entirely)
- fueling-flag classification at a future workout's `start_at`, for both a
  `>0` and a `<=0` balance case

Plus: no-target raises `NoTargetSetError` (the domain function has no
sensible partial timeline to return without a base_calories figure).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import PlannedWorkout, PlannedWorkoutSource, PlannedWorkoutStatus
from app.domain.energy_balance import compute_energy_timeline
from app.domain.errors import NoTargetSetError

# A far-future, distinctive date: this test suite runs against a shared dev
# Neon database (see api/.env), not an ephemeral per-run DB, and several
# other route-level test suites in this repo commit real rows outside the
# transactional-rollback fixture (confirmed: committed `meals` rows already
# exist on the commonly-reused `date(2026, 7, 26)` FROZEN_INSTANT date used
# elsewhere in this suite). `compute_energy_timeline` queries "all meals /
# workouts for this local_date" with no other scoping, so it would pick up
# that unrelated committed data. Using a date nothing else in the repo
# reuses sidesteps the collision instead of masking it.
DAY = date(2031, 11, 3)


def _make_workout(session: Session, **overrides: object) -> PlannedWorkout:
    values: dict[str, object] = {
        "external_id": None,
        "source": PlannedWorkoutSource.manual,
        "local_date": DAY,
        "start_at": datetime(2031, 11, 3, 8, 0, tzinfo=UTC),
        "duration_minutes": 60,
        "sport_type": None,
        "icu_joules": None,
        "estimated_calories": None,
        "actual_calories": None,
        "status": PlannedWorkoutStatus.planned,
        "fetched_at": datetime(2031, 11, 3, 6, 0, tzinfo=UTC),
    }
    values.update(overrides)
    workout = PlannedWorkout(**values)
    session.add(workout)
    session.flush()
    return workout


class TestNoTarget:
    def test_raises_when_no_target_set(self, db_session: Session) -> None:
        # No `make_target` call in this test -- but targets are versioned
        # rows that persist indefinitely once set (never deleted), and this
        # suite runs against a shared dev DB (see the `DAY` comment above),
        # so a day far enough in the *past* -- before any real target's
        # earliest `effective_from` -- is what actually guarantees "no
        # target applies", not just omitting `make_target` in this test.
        no_target_day = date(2000, 1, 1)
        now = datetime(2000, 1, 1, 12, 0, tzinfo=UTC)

        with pytest.raises(NoTargetSetError):
            compute_energy_timeline(db_session, day=no_target_day, now=now)


class TestFlatBasalLine:
    def test_no_meals_or_workouts_is_a_flat_basal_drain(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        now = datetime(2031, 11, 3, 6, 0, tzinfo=UTC)  # local midnight + 360 min

        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert timeline.events == []
        assert timeline.fueling_flags == []
        assert timeline.end_of_day_target == 2400

        # rate = 2400/1440 kcal/min = 1.66667; 360 min elapsed -> -600
        assert timeline.current_balance == -600
        assert timeline.points[0].balance == 0
        assert timeline.points[-1].balance == -600
        assert timeline.points[-1].at == now

        # predicted end of day: 1439 minutes of basal drain from midnight
        expected_eod = round(Decimal(2400) / Decimal(1440) * Decimal(1439))
        assert timeline.predicted_end_of_day == -expected_eod
        assert timeline.forecast_points[0].balance == -600
        assert timeline.forecast_points[-1].balance == -expected_eod


class TestPastMealAndWorkout:
    def test_solid_line_steps_for_past_meal_and_past_workout(
        self, db_session: Session, make_target, make_meal, make_meal_item, make_food
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        food = make_food(calories=Decimal("200"))
        meal_time = datetime(2031, 11, 3, 8, 0, tzinfo=UTC)
        meal = make_meal(logged_at=meal_time, local_date=DAY)
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        workout_time = datetime(2031, 11, 3, 9, 0, tzinfo=UTC)
        workout = _make_workout(
            db_session,
            status=PlannedWorkoutStatus.completed,
            source=PlannedWorkoutSource.intervals_completed,
            start_at=workout_time,
            actual_calories=300,
        )

        now = datetime(2031, 11, 3, 10, 0, tzinfo=UTC)  # 600 min after midnight
        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert {(e.kind, e.delta_kcal, e.status) for e in timeline.events} == {
            ("meal", 200, None),
            ("workout", -300, "completed"),
        }

        rate = Decimal(2400) / Decimal(1440)  # basal kcal drained per minute
        # 0 -> +200 at 08:00 (480 min) -> -300 at 09:00 (540 min) -> drain to 10:00 (600 min)
        balance_at_meal = -rate * Decimal(480)
        balance_after_meal = balance_at_meal + Decimal(200)
        balance_at_workout = balance_after_meal - rate * Decimal(60)
        balance_after_workout = balance_at_workout - Decimal(300)
        balance_at_now = balance_after_workout - rate * Decimal(60)

        assert timeline.current_balance == round(balance_at_now)
        assert workout.id is not None


class TestFutureMealAndWorkout:
    def test_dashed_line_includes_future_logged_meal_and_future_planned_workout(
        self, db_session: Session, make_target, make_meal, make_meal_item, make_food
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        now = datetime(2031, 11, 3, 6, 0, tzinfo=UTC)

        food = make_food(calories=Decimal("400"))
        future_meal_time = datetime(2031, 11, 3, 12, 0, tzinfo=UTC)
        meal = make_meal(logged_at=future_meal_time, local_date=DAY)
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        future_workout_time = datetime(2031, 11, 3, 18, 0, tzinfo=UTC)
        _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=future_workout_time,
            icu_joules=5000,
            estimated_calories=350,
        )

        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        # Nothing yet on the solid line -- both events are in the future.
        assert timeline.current_balance == -600

        assert {(e.kind, e.delta_kcal) for e in timeline.events} == {
            ("meal", 400),
            ("workout", -350),
        }

        # zero-further-intake forecast still includes these known future steps
        rate = Decimal(2400) / Decimal(1440)  # basal kcal drained per minute
        balance_at_now = -Decimal(600)
        balance_at_meal = balance_at_now - rate * Decimal(360)  # 06:00 -> 12:00 = 360 min
        balance_after_meal = balance_at_meal + Decimal(400)
        balance_at_workout = balance_after_meal - rate * Decimal(360)  # 12:00 -> 18:00
        balance_after_workout = balance_at_workout - Decimal(350)
        balance_at_eod = balance_after_workout - rate * Decimal(359)  # 18:00 -> 23:59

        assert timeline.predicted_end_of_day == round(balance_at_eod)


class TestGracePeriod:
    def test_planned_workout_past_grace_window_is_dropped(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        now = datetime(2031, 11, 3, 14, 0, tzinfo=UTC)
        # start_at + 4h < now -> grace period expired, never confirmed completed
        start_at = datetime(2031, 11, 3, 9, 0, tzinfo=UTC)
        _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=start_at,
            icu_joules=4000,
            estimated_calories=280,
        )

        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert timeline.events == []
        rate = Decimal(2400) / Decimal(1440)
        assert timeline.current_balance == round(-rate * Decimal(840))  # 14:00 = 840 min

    def test_planned_workout_within_grace_window_still_counts(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        # 3 hours after start_at -- inside the 4h grace period.
        now = datetime(2031, 11, 3, 12, 0, tzinfo=UTC)
        start_at = datetime(2031, 11, 3, 9, 0, tzinfo=UTC)
        _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=start_at,
            icu_joules=4000,
            estimated_calories=280,
        )

        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert len(timeline.events) == 1
        assert timeline.events[0].delta_kcal == -280


class TestNullEstimatedCaloriesExcluded:
    def test_planned_workout_with_no_icu_joules_is_excluded_entirely(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        now = datetime(2031, 11, 3, 12, 0, tzinfo=UTC)
        _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=datetime(2031, 11, 3, 8, 0, tzinfo=UTC),
            icu_joules=None,
            estimated_calories=None,
        )
        # Also a future one, to confirm exclusion isn't just a past-only thing.
        _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=datetime(2031, 11, 3, 18, 0, tzinfo=UTC),
            icu_joules=None,
            estimated_calories=None,
        )

        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert timeline.events == []
        assert timeline.fueling_flags == []
        rate = Decimal(2400) / Decimal(1440)
        assert timeline.current_balance == round(-rate * Decimal(720))  # 12:00 = 720 min


class TestNowOutsideDay:
    """`now` is clamped into [local_midnight, local_end_of_day] for `day`
    before use, so viewing a past or future day's energy timeline (not just
    today's) produces a sensible line instead of a negative-duration walk.
    """

    def test_viewing_a_past_day_is_entirely_solid(
        self, db_session: Session, make_target, make_meal, make_meal_item, make_food
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        food = make_food(calories=Decimal("200"))
        meal = make_meal(logged_at=datetime(2031, 11, 3, 8, 0, tzinfo=UTC), local_date=DAY)
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        # Real "now" is several days after DAY -- viewing a past day.
        now = datetime(2031, 11, 8, 9, 0, tzinfo=UTC)
        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        # Nothing left to forecast -- current_balance already is the day's
        # final balance, and the forecast segment is a degenerate single
        # point rather than a negative-duration walk backwards.
        assert timeline.current_balance == timeline.predicted_end_of_day
        assert all(p.balance == timeline.current_balance for p in timeline.forecast_points)

        rate = Decimal(2400) / Decimal(1440)
        balance_at_meal = -rate * Decimal(480)  # 08:00 = 480 min
        balance_after_meal = balance_at_meal + Decimal(200)
        expected_eod = balance_after_meal - rate * Decimal(959)  # 08:00 -> 23:59 = 959 min
        assert timeline.current_balance == round(expected_eod)

    def test_viewing_a_future_day_is_entirely_forecast(
        self, db_session: Session, make_target, make_meal, make_meal_item, make_food
    ) -> None:
        make_target(effective_from=date(2031, 1, 1), base_calories=2400)
        food = make_food(calories=Decimal("400"))
        meal = make_meal(logged_at=datetime(2031, 11, 3, 8, 0, tzinfo=UTC), local_date=DAY)
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        # Real "now" is days before DAY -- viewing a future day.
        now = datetime(2031, 10, 29, 9, 0, tzinfo=UTC)
        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        # Nothing has happened yet on that day -- the solid line is a
        # degenerate single point at local midnight, balance 0.
        assert timeline.current_balance == 0
        assert all(p.balance == 0 for p in timeline.points)

        rate = Decimal(2400) / Decimal(1440)
        balance_at_meal = -rate * Decimal(480)
        balance_after_meal = balance_at_meal + Decimal(400)
        expected_eod = balance_after_meal - rate * Decimal(959)
        assert timeline.predicted_end_of_day == round(expected_eod)

    def test_grace_period_uses_real_now_not_the_day_clamped_now(
        self, db_session: Session, make_target
    ) -> None:
        # start_at is late in DAY, so the day-clamped "now" (23:59 on DAY)
        # would still be inside the 4h grace window -- but the *real* now,
        # several days later, is well past it. The workout must be dropped.
        start_at = datetime(2031, 11, 3, 23, 0, tzinfo=UTC)
        _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=start_at,
            icu_joules=4000,
            estimated_calories=280,
        )
        make_target(effective_from=DAY, base_calories=2400)

        now = datetime(2031, 11, 8, 9, 0, tzinfo=UTC)
        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert timeline.events == []


class TestFuelingFlags:
    def test_well_fueled_when_balance_positive_at_start_at(
        self, db_session: Session, make_target, make_meal, make_meal_item, make_food
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        now = datetime(2031, 11, 3, 6, 0, tzinfo=UTC)

        # A big future meal well before the workout keeps the balance positive.
        food = make_food(calories=Decimal("2000"))
        meal = make_meal(logged_at=datetime(2031, 11, 3, 8, 0, tzinfo=UTC), local_date=DAY)
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        workout = _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=datetime(2031, 11, 3, 18, 0, tzinfo=UTC),
            icu_joules=5000,
            estimated_calories=350,
        )

        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert len(timeline.fueling_flags) == 1
        flag = timeline.fueling_flags[0]
        assert flag.workout_id == workout.id
        assert flag.status == "well_fueled"
        assert flag.at == workout.start_at

    def test_under_fueled_when_balance_non_positive_at_start_at(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=DAY, base_calories=2400)
        now = datetime(2031, 11, 3, 6, 0, tzinfo=UTC)

        # No meals at all -- pure basal drain keeps balance negative all day.
        workout = _make_workout(
            db_session,
            status=PlannedWorkoutStatus.planned,
            source=PlannedWorkoutSource.intervals_planned,
            start_at=datetime(2031, 11, 3, 18, 0, tzinfo=UTC),
            icu_joules=5000,
            estimated_calories=350,
        )

        timeline = compute_energy_timeline(db_session, day=DAY, now=now)

        assert len(timeline.fueling_flags) == 1
        flag = timeline.fueling_flags[0]
        assert flag.workout_id == workout.id
        assert flag.status == "under_fueled"
