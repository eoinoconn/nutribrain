"""Live Energy chart domain logic (EC-05, §5 of docs/features/energy_balance_chart.md).

``compute_energy_timeline`` builds a step-function net-kcal-balance timeline
for one local day: a solid "so far" line from local midnight to ``now``, a
dashed forecast line from ``now`` to local end-of-day under a
zero-further-intake assumption, event markers for meals/workouts, and a
fueling classification for each future planned workout.

Also home to ``KCAL_PER_KILOJOULE`` / ``estimate_workout_calories`` (§3
"Workout calorie estimation"), relocated here from
``app/domain/planned_workouts.py`` now that this module exists — EC-03 had
parked them there to avoid colliding with this module being built in
parallel; ``planned_workouts.py`` now imports them from here instead.

## Design notes (documented per the task brief's ambiguity call-outs)

**Timezone for local-midnight/end-of-day bounds:** always resolved from
``get_settings(session).local_timezone`` (the account-level setting, §6a),
never from an individual ``Meal.local_tz``. The whole day's basal-drain line
needs one single consistent timezone reference regardless of individual meal
timestamps — mixing per-meal timezones would make the constant per-minute
basal rate (§5 step 1) ill-defined at day boundaries, and the account
setting is exactly the "whose midnight is this" source of truth §6a
introduces for this feature.

**Rounding boundary:** all intermediate accumulation (basal drain, step
deltas, running balance) is done in ``Decimal``, never ``float``, per
``docs/style.md``. Rounding to ``int`` happens only when values cross into a
DTO field (``EnergyPoint.balance``, ``EnergyTimeline.current_balance`` /
``predicted_end_of_day``) — i.e. this domain function's public return value
is treated as the "final serialization" boundary docs/style.md refers to,
since nothing downstream of it does further math on these numbers before
display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import Food, Meal, PlannedWorkout, PlannedWorkoutStatus
from app.domain.dto import EnergyEvent, EnergyPoint, EnergyTimeline, FuelingFlag
from app.domain.errors import NaiveDatetimeError, NoTargetSetError
from app.domain.nutrition_math import compute_item_macros
from app.domain.settings import get_settings
from app.domain.targets import get_effective_target

# §3 "Workout calorie estimation": one frozen domain constant, not scattered
# magic numbers. Derived from three of this athlete's own completed rides
# (1.17, 0.96, 1.23 kcal/kJ observed) against the literature's ~1.0-1.05
# convention -- see the spec doc for the full derivation. Not user-configurable
# in v1 (tracked for a future app_settings field, EC-11).
KCAL_PER_KILOJOULE = 1.1

# A `planned` row (never confirmed completed by sync) only counts toward the
# line for 4 hours past its start_at -- past that, treat it as skipped
# rather than keeping a phantom deficit (§5 step 3, "Grace period").
_GRACE_PERIOD = timedelta(hours=4)


def estimate_workout_calories(icu_joules: int) -> int:
    """Flat kJ -> kcal conversion for a planned workout that has icu_joules.

    ``round(icu_joules / 1000 * KCAL_PER_KILOJOULE)`` per §3 "Workout calorie
    estimation" -- no historical-data lookup, no per-athlete calibration.
    """

    return round(icu_joules / 1000 * KCAL_PER_KILOJOULE)


@dataclass(frozen=True, slots=True)
class _Step:
    """One internal step-function event: a meal or a workout."""

    at: datetime
    delta_kcal: Decimal
    kind: Literal["meal", "workout"]
    status: Literal["planned", "completed"] | None
    workout_id: int | None


def compute_energy_timeline(session: Session, *, day: date, now: datetime) -> EnergyTimeline:
    """Compute the Live Energy step-function timeline for one local day.

    Args:
        session: Active SQLAlchemy session.
        day: The local_date to compute the timeline for.
        now: Timezone-aware "current instant" — solid/dashed split point.

    Returns:
        EnergyTimeline per §5.

    Raises:
        NaiveDatetimeError: If ``now`` is not timezone-aware.
        NoTargetSetError: If no effective target exists for ``day`` — the
            basal-drain rate has nothing to divide, so there's no timeline
            to compute (see ``NoTargetSetError``'s docstring).
    """

    if now.tzinfo is None:
        raise NaiveDatetimeError(field="now")

    app_settings = get_settings(session)
    tz = ZoneInfo(app_settings.local_timezone)
    local_midnight = datetime.combine(day, time.min, tzinfo=tz)
    # "local 23:59" per §5 step 6 (predicted_end_of_day is evaluated there),
    # taken literally rather than rounding up to the next midnight.
    local_end_of_day = datetime.combine(day, time(23, 59), tzinfo=tz)

    effective_target = get_effective_target(session, day=day)
    if effective_target is None:
        raise NoTargetSetError(day)

    # Negative: basal metabolism drains the balance over time (§5 step 1).
    basal_rate_per_minute = -Decimal(effective_target.base_calories) / Decimal(1440)

    steps = _build_steps(session, day=day, now=now)
    steps.sort(key=lambda s: s.at)

    solid_steps = [s for s in steps if s.at <= now]
    forecast_steps = [s for s in steps if s.at > now]

    solid_points, balance_at_now, _ = _walk_segment(
        start_at=local_midnight,
        start_balance=Decimal(0),
        end_at=now,
        steps=solid_steps,
        basal_rate_per_minute=basal_rate_per_minute,
    )
    forecast_points, balance_at_eod, forecast_step_balances = _walk_segment(
        start_at=now,
        start_balance=balance_at_now,
        end_at=local_end_of_day,
        steps=forecast_steps,
        basal_rate_per_minute=basal_rate_per_minute,
    )

    fueling_flags: list[FuelingFlag] = []
    for step, balance_before in forecast_step_balances:
        if step.kind != "workout" or step.status != "planned" or step.workout_id is None:
            continue
        fueling_flags.append(
            FuelingFlag(
                workout_id=step.workout_id,
                at=step.at,
                status="well_fueled" if balance_before > 0 else "under_fueled",
            )
        )

    events = [
        EnergyEvent(
            at=step.at,
            delta_kcal=_round_kcal(step.delta_kcal),
            kind=step.kind,
            status=step.status,
        )
        for step in steps
    ]

    return EnergyTimeline(
        points=solid_points,
        forecast_points=forecast_points,
        events=events,
        current_balance=_round_kcal(balance_at_now),
        predicted_end_of_day=_round_kcal(balance_at_eod),
        end_of_day_target=effective_target.effective_calories,
        fueling_flags=fueling_flags,
    )


def _build_steps(session: Session, *, day: date, now: datetime) -> list[_Step]:
    """Build the unordered list of meal and workout steps for ``day``.

    Meal totals reuse ``compute_item_macros`` (the same read-time macro
    computation ``get_day`` uses) rather than recomputing macros separately.
    Workout steps apply §5 step 3's rules: completed rows use
    ``actual_calories``; planned rows use ``estimated_calories`` and are
    skipped entirely when it's null (no icu_joules -> not fueling-relevant)
    or once past their 4-hour grace period with no completion (treated as
    skipped, dropped from both the line and the event/marker list — a
    marker for a workout likely-skipped-and-uncompleted would be as
    misleading as the phantom deficit itself).
    """

    steps: list[_Step] = []

    meals = session.scalars(
        select(Meal).where(Meal.local_date == day).options(selectinload(Meal.items))
    ).unique()

    meal_list = list(meals)
    food_map = _load_foods_for_meals(session, meal_list)

    for meal in meal_list:
        total = Decimal(0)
        for item in meal.items:
            food = food_map.get(item.food_id) if item.food_id is not None else None
            macros = compute_item_macros(item, food)
            total += macros.calories
        steps.append(
            _Step(
                at=meal.logged_at,
                delta_kcal=total,
                kind="meal",
                status=None,
                workout_id=None,
            )
        )

    workouts = session.scalars(select(PlannedWorkout).where(PlannedWorkout.local_date == day))

    for workout in workouts:
        if workout.status == PlannedWorkoutStatus.completed:
            if workout.actual_calories is None:
                continue
            steps.append(
                _Step(
                    at=workout.start_at,
                    delta_kcal=-Decimal(workout.actual_calories),
                    kind="workout",
                    status="completed",
                    workout_id=workout.id,
                )
            )
            continue

        # status == planned
        if workout.estimated_calories is None:
            continue  # no icu_joules -> not fueling-relevant, no step/marker
        if workout.start_at <= now and now > workout.start_at + _GRACE_PERIOD:
            continue  # grace period expired, never confirmed completed
        steps.append(
            _Step(
                at=workout.start_at,
                delta_kcal=-Decimal(workout.estimated_calories),
                kind="workout",
                status="planned",
                workout_id=workout.id,
            )
        )

    return steps


def _load_foods_for_meals(session: Session, meals: list[Meal]) -> dict[int, Food]:
    """Batch-load foods referenced by meal items (mirrors day_aggregation's helper)."""

    food_ids: set[int] = set()
    for meal in meals:
        for item in meal.items:
            if item.food_id is not None:
                food_ids.add(item.food_id)

    if not food_ids:
        return {}

    foods = session.scalars(select(Food).where(Food.id.in_(food_ids)))
    return {f.id: f for f in foods}


def _walk_segment(
    *,
    start_at: datetime,
    start_balance: Decimal,
    end_at: datetime,
    steps: list[_Step],
    basal_rate_per_minute: Decimal,
) -> tuple[list[EnergyPoint], Decimal, list[tuple[_Step, Decimal]]]:
    """Walk one segment (solid or forecast) applying basal drain + steps.

    Basal drain accrues continuously (linear ramp) between steps; each step
    applies an instant vertical jump at its own timestamp (§5 step 3: "not
    distributed over duration_minutes"). Two ``EnergyPoint``s are emitted per
    step (balance immediately before and immediately after the jump) so a
    straight-line-interpolating chart renders the discontinuity correctly.

    Returns the rounded-for-display point list, the segment's raw (Decimal,
    unrounded) end balance for the caller to continue accumulating into the
    next segment, and a list of ``(step, balance_before_step)`` pairs used to
    evaluate fueling flags at the balance a workout's own step hasn't yet
    been subtracted from ("how fueled going into this session").
    """

    points = [EnergyPoint(at=start_at, balance=_round_kcal(start_balance))]
    step_balances: list[tuple[_Step, Decimal]] = []

    running_at = start_at
    running_balance = start_balance

    for step in steps:
        elapsed_minutes = Decimal((step.at - running_at).total_seconds()) / Decimal(60)
        running_balance += basal_rate_per_minute * elapsed_minutes
        points.append(EnergyPoint(at=step.at, balance=_round_kcal(running_balance)))
        step_balances.append((step, running_balance))

        running_balance += step.delta_kcal
        points.append(EnergyPoint(at=step.at, balance=_round_kcal(running_balance)))

        running_at = step.at

    elapsed_minutes = Decimal((end_at - running_at).total_seconds()) / Decimal(60)
    running_balance += basal_rate_per_minute * elapsed_minutes
    points.append(EnergyPoint(at=end_at, balance=_round_kcal(running_balance)))

    return points, running_balance, step_balances


def _round_kcal(value: Decimal) -> int:
    """Round a Decimal kcal balance to the nearest whole kcal at the DTO boundary."""

    return round(value)
