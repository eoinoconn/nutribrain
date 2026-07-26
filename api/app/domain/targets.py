"""Targets domain logic (T-025, §3, §4).

``set_target`` always inserts a new versioned row — it never mutates an existing
target.  ``get_effective_target`` resolves the latest target where
``effective_from <= date`` and combines it with the cached calories_out for that
date when present.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import IntervalsCaloriesOut, Target
from app.domain.dto import EffectiveTarget, SetTargetResult, TargetRow


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
    When an ``intervals_calories_out`` cache row exists for the day, its value is
    added to the base to produce ``effective_calories``.  A missing cache row
    falls back to base alone (``calories_out`` will be None) — distinct from a
    cached zero which represents a genuine rest day.
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

    # Look up cached activity calories for the day
    cache_stmt = select(IntervalsCaloriesOut).where(IntervalsCaloriesOut.date == day)
    cache_row = session.scalar(cache_stmt)

    calories_out: int | None = None
    effective_calories = target.base_calories
    if cache_row is not None:
        calories_out = cache_row.calories_out
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
