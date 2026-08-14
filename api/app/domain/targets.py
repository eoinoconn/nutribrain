"""Targets domain logic (T-025, §3, §4).

``set_target`` always inserts a new versioned row — it never mutates an existing
target.  ``get_effective_target`` resolves the latest target where
``effective_from <= date`` and combines it with the resolved calories_out for
that date when present.

Calories-out sourcing (EC-07, "Reconciling calories-out"): a day's
``calories_out`` is ``sum(planned_workouts.actual_calories where
status='completed' and local_date=day)`` at read time, unless a manual
override row exists in ``intervals_calories_out`` (``source='manual'``),
which still wins — this is the single source of truth shared by the target
panel (here, and via ``day_aggregation.get_day``/``get_range``) and the
energy chart's workout total. ``fetch_activity_calories_by_day`` and its
sync-populated ``intervals_calories_out`` rows are retired; only
manual-override rows are written to that table now (``set_manual_calories_out``
in ``intervals_sync.py``).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import (
    IntervalsCaloriesOut,
    IntervalsSource,
    PlannedWorkout,
    PlannedWorkoutStatus,
    Target,
)
from app.domain.dto import EffectiveTarget, SetTargetResult, TargetRow
from app.logging import get_logger

logger = get_logger(__name__)


def set_target(
    session: Session,
    *,
    base_calories: int,
    protein_g: int,
    carbs_g: int,
    fat_g: int,
    effective_from: date,
) -> SetTargetResult:
    """Insert a new versioned target row (never mutates existing).

    Returns the new target and whether it overlaps (i.e. replaces) an earlier
    same-day target.
    """

    # Check if a target already exists for this effective_from date
    same_day_stmt = select(Target).where(Target.effective_from == effective_from).limit(1)
    same_day_overlap = session.scalar(same_day_stmt) is not None

    target = Target(
        effective_from=effective_from,
        base_calories=base_calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )
    session.add(target)
    session.flush()

    logger.info("target_set", target_id=target.id, effective_from=str(target.effective_from))

    return SetTargetResult(
        id=target.id,
        effective_from=target.effective_from,
        base_calories=target.base_calories,
        protein_g=target.protein_g,
        carbs_g=target.carbs_g,
        fat_g=target.fat_g,
        same_day_overlap=same_day_overlap,
    )


def list_targets(session: Session) -> list[TargetRow]:
    """Return all targets ordered by effective_from descending (versioned history)."""

    stmt = select(Target).order_by(Target.effective_from.desc(), Target.id.desc())
    targets = session.scalars(stmt).all()
    return [
        TargetRow(
            id=t.id,
            effective_from=t.effective_from,
            base_calories=t.base_calories,
            protein_g=t.protein_g,
            carbs_g=t.carbs_g,
            fat_g=t.fat_g,
            created_at=t.created_at,
        )
        for t in targets
    ]


def get_effective_target(
    session: Session,
    *,
    day: date,
) -> EffectiveTarget | None:
    """Return the effective target for ``day``, or None if no target is set.

    The effective target is the most recent target where ``effective_from <= day``.
    ``calories_out`` is resolved via ``resolve_calories_out`` (EC-07) and added
    to the base to produce ``effective_calories``. A day with neither a manual
    override nor a completed workout falls back to base alone (``calories_out``
    is None) — distinct from an explicit 0, which represents a genuine
    completed-but-zero-calorie day.
    """

    target_stmt = (
        select(Target)
        .where(Target.effective_from <= day)
        .order_by(Target.effective_from.desc(), Target.id.desc())
        .limit(1)
    )
    target = session.scalar(target_stmt)

    if target is None:
        return None

    calories_out = resolve_calories_out(session, day)
    effective_calories = target.base_calories
    if calories_out is not None:
        effective_calories = target.base_calories + calories_out

    return EffectiveTarget(
        effective_from=target.effective_from,
        base_calories=target.base_calories,
        protein_g=target.protein_g,
        carbs_g=target.carbs_g,
        fat_g=target.fat_g,
        calories_out=calories_out,
        effective_calories=effective_calories,
    )


def resolve_calories_out(session: Session, day: date) -> int | None:
    """Resolve a single day's calories-out (EC-07, "Reconciling calories-out").

    A manual override row in ``intervals_calories_out`` (``source='manual'``)
    always wins. Otherwise, ``calories_out`` is the sum of
    ``planned_workouts.actual_calories`` for completed workouts on that day —
    ``None`` when there is neither an override nor any completed workout,
    distinct from an explicit sum of 0 (a completed workout that genuinely
    reported zero calories).
    """

    manual_row = session.scalar(
        select(IntervalsCaloriesOut).where(
            IntervalsCaloriesOut.date == day,
            IntervalsCaloriesOut.source == IntervalsSource.manual,
        )
    )
    if manual_row is not None:
        return manual_row.calories_out

    total = session.scalar(
        select(func.sum(PlannedWorkout.actual_calories)).where(
            PlannedWorkout.local_date == day,
            PlannedWorkout.status == PlannedWorkoutStatus.completed,
        )
    )
    return int(total) if total is not None else None


def resolve_calories_out_map(
    session: Session,
    *,
    from_date: date,
    to_date: date,
) -> dict[date, int]:
    """Batch version of ``resolve_calories_out`` over ``[from_date, to_date]``.

    Two bounded queries (manual overrides + a grouped sum), for range
    aggregation (``day_aggregation.get_range``) instead of one resolver call
    per day. Only days with a resolved value (override or completed workout)
    appear in the result, matching ``resolve_calories_out``'s None-for-missing
    semantics via ``dict.get``.
    """

    manual_stmt = select(IntervalsCaloriesOut).where(
        IntervalsCaloriesOut.date >= from_date,
        IntervalsCaloriesOut.date <= to_date,
        IntervalsCaloriesOut.source == IntervalsSource.manual,
    )
    manual_map = {row.date: row.calories_out for row in session.scalars(manual_stmt)}

    sum_stmt = (
        select(PlannedWorkout.local_date, func.sum(PlannedWorkout.actual_calories))
        .where(
            PlannedWorkout.local_date >= from_date,
            PlannedWorkout.local_date <= to_date,
            PlannedWorkout.status == PlannedWorkoutStatus.completed,
        )
        .group_by(PlannedWorkout.local_date)
    )
    summed_map = {
        local_date: int(total)
        for local_date, total in session.execute(sum_stmt)
        if total is not None
    }

    result = dict(summed_map)
    result.update(manual_map)  # manual overrides win
    return result
