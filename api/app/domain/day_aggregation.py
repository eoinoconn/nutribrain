"""Day and range aggregation (T-027).

Implements §4 read tools: get_day and get_range. All macro computation happens
at read time — no snapshotting. Queries are bounded: meals, items, and referenced
foods are loaded in a fixed number of queries regardless of data volume.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import Food, Meal, MealType, Target
from app.domain.dto import (
    DayMealGroup,
    DayResponse,
    EffectiveTarget,
    ItemMacros,
    MealItemResponse,
    PeriodTotals,
    RangeResponse,
)
from app.domain.nutrition_math import compute_item_macros
from app.domain.targets import get_effective_target, resolve_calories_out_map


def get_day(session: Session, *, day: date) -> DayResponse:
    """Aggregate a single day: meals grouped by type, totals, target, delta.

    Loads meals + items + foods in bounded queries (no N+1). Macros are computed
    at read time from the current food nutrition values.

    Args:
        session: Active SQLAlchemy session.
        day: The local_date to aggregate.

    Returns:
        DayResponse with meals grouped by meal_type, day totals, effective
        target, and delta vs. target.
    """

    # One query: meals with items eagerly loaded for this day
    meals = _load_meals_for_dates(session, day, day)

    # Batch-load all referenced foods
    food_map = _load_foods_for_meals(session, meals)

    # Build grouped response
    grouped: dict[MealType, list[DayMealGroup]] = {}
    day_totals = _zero_macros()

    for meal in meals:
        meal_items_resp, meal_totals = _compute_meal_items(meal, food_map)
        day_totals = _add_macros(day_totals, meal_totals)

        group = DayMealGroup(
            id=meal.id,
            logged_at=meal.logged_at,
            meal_type=meal.meal_type,
            notes=meal.notes,
            items=meal_items_resp,
            totals=meal_totals,
        )
        grouped.setdefault(meal.meal_type, []).append(group)

    # Effective target
    effective_target = _get_effective_target(session, day)

    # Delta vs target
    delta: ItemMacros | None = None
    if effective_target is not None:
        delta = ItemMacros(
            calories=day_totals.calories - Decimal(str(effective_target.effective_calories)),
            protein_g=day_totals.protein_g - Decimal(str(effective_target.protein_g)),
            carbs_g=day_totals.carbs_g - Decimal(str(effective_target.carbs_g)),
            fat_g=day_totals.fat_g - Decimal(str(effective_target.fat_g)),
            fiber_g=day_totals.fiber_g,
            sat_fat_g=day_totals.sat_fat_g,
            sodium_mg=day_totals.sodium_mg,
        )

    return DayResponse(
        date=day,
        meals=grouped,
        day_totals=day_totals,
        effective_target=effective_target,
        delta_vs_target=delta,
    )


def get_range(
    session: Session,
    *,
    from_date: date,
    to_date: date,
    granularity: str = "day",
) -> RangeResponse:
    """Aggregate a date range with per-period totals, targets, and adherence.

    Loads all meals in the range in bounded queries, then groups by period
    (day or week). Macros are computed at read time.

    Args:
        session: Active SQLAlchemy session.
        from_date: Start date (inclusive).
        to_date: End date (inclusive).
        granularity: "day" or "week".

    Returns:
        RangeResponse with per-period totals, effective targets, and adherence.

    Raises:
        ValueError: If granularity is not "day" or "week".
    """

    if granularity not in ("day", "week"):
        raise ValueError(f"granularity must be 'day' or 'week', got '{granularity}'")

    # One query: all meals in range with items eagerly loaded
    meals = _load_meals_for_dates(session, from_date, to_date)

    # Batch-load all referenced foods
    food_map = _load_foods_for_meals(session, meals)

    # Compute per-meal totals indexed by local_date
    daily_totals: dict[date, ItemMacros] = {}
    for meal in meals:
        _, meal_totals = _compute_meal_items(meal, food_map)
        if meal.local_date in daily_totals:
            daily_totals[meal.local_date] = _add_macros(daily_totals[meal.local_date], meal_totals)
        else:
            daily_totals[meal.local_date] = meal_totals

    # Build periods
    periods = _build_periods(session, from_date, to_date, granularity, daily_totals)

    return RangeResponse(
        from_date=from_date,
        to_date=to_date,
        granularity=granularity,
        periods=periods,
    )


# --- Internal helpers -------------------------------------------------------


def _load_meals_for_dates(session: Session, start: date, end: date) -> list[Meal]:
    """Load meals in [start, end] with items eagerly loaded (1 query + 1 subquery)."""

    stmt = (
        select(Meal)
        .where(Meal.local_date >= start, Meal.local_date <= end)
        .options(selectinload(Meal.items))
        .order_by(Meal.logged_at)
    )
    return list(session.scalars(stmt).unique())


def _load_foods_for_meals(session: Session, meals: list[Meal]) -> dict[int, Food]:
    """Batch-load all foods referenced by meal items (1 query)."""

    food_ids: set[int] = set()
    for meal in meals:
        for item in meal.items:
            if item.food_id is not None:
                food_ids.add(item.food_id)

    if not food_ids:
        return {}

    stmt = select(Food).where(Food.id.in_(food_ids))
    foods = session.scalars(stmt).all()
    return {f.id: f for f in foods}


def _compute_meal_items(
    meal: Meal,
    food_map: dict[int, Food],
) -> tuple[list[MealItemResponse], ItemMacros]:
    """Compute item macros and meal totals from eagerly-loaded data."""

    items_resp: list[MealItemResponse] = []
    meal_totals = _zero_macros()

    for item in meal.items:
        food = food_map.get(item.food_id) if item.food_id is not None else None
        macros = compute_item_macros(item, food)
        meal_totals = _add_macros(meal_totals, macros)

        items_resp.append(
            MealItemResponse(
                id=item.id,
                food_id=item.food_id,
                name=item.name,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                source=item.source,
                macros=macros,
            )
        )

    return items_resp, meal_totals


def _get_effective_target(session: Session, day: date) -> EffectiveTarget | None:
    """Compute the effective target for a single day.

    Delegates to ``targets.get_effective_target`` (EC-07) so this module has
    no separate calories_out sourcing to keep in sync with the target panel.
    """

    return get_effective_target(session, day=day)


def _get_effective_targets_for_range(
    session: Session,
    from_date: date,
    to_date: date,
) -> dict[date, EffectiveTarget]:
    """Batch-load effective targets for a date range in bounded queries.

    Loads all targets and resolves calories_out (EC-07: completed
    planned_workouts, or a manual override) for the range, then computes
    per-day effective targets in memory.
    """

    # Load all targets that could apply (effective_from <= to_date)
    targets = list(
        session.scalars(
            select(Target)
            .where(Target.effective_from <= to_date)
            .order_by(Target.effective_from.desc())
        )
    )

    if not targets:
        return {}

    calories_out_map = resolve_calories_out_map(session, from_date=from_date, to_date=to_date)

    # Build per-day targets
    result: dict[date, EffectiveTarget] = {}
    current = from_date
    while current <= to_date:
        # Find the applicable target (first with effective_from <= current)
        applicable = None
        for t in targets:
            if t.effective_from <= current:
                applicable = t
                break

        if applicable is not None:
            cal_out = calories_out_map.get(current)
            effective_calories = applicable.base_calories
            if cal_out is not None:
                effective_calories += cal_out
            result[current] = EffectiveTarget(
                effective_from=applicable.effective_from,
                base_calories=applicable.base_calories,
                protein_g=applicable.protein_g,
                carbs_g=applicable.carbs_g,
                fat_g=applicable.fat_g,
                calories_out=cal_out,
                effective_calories=effective_calories,
            )

        current += timedelta(days=1)

    return result


def _build_periods(
    session: Session,
    from_date: date,
    to_date: date,
    granularity: str,
    daily_totals: dict[date, ItemMacros],
) -> list[PeriodTotals]:
    """Build period aggregations for the range."""

    # Batch-load targets for the entire range
    targets_map = _get_effective_targets_for_range(session, from_date, to_date)

    if granularity == "day":
        periods: list[PeriodTotals] = []
        current = from_date
        while current <= to_date:
            totals = daily_totals.get(current, _zero_macros())
            target = targets_map.get(current)
            adherence: bool | None = None
            if target is not None:
                adherence = totals.calories <= Decimal(str(target.effective_calories))
            periods.append(
                PeriodTotals(
                    period_start=current,
                    period_end=current,
                    totals=totals,
                    effective_target=target,
                    adherence=adherence,
                )
            )
            current += timedelta(days=1)
        return periods

    # Weekly aggregation: ISO weeks starting from Monday
    periods = []
    current = from_date
    while current <= to_date:
        # Find the Monday of this week (or from_date if it's later)
        week_start = current - timedelta(days=current.weekday())
        if week_start < from_date:
            week_start = from_date
        # Find the Sunday of this week (or to_date if it's earlier)
        week_end = week_start + timedelta(days=6 - week_start.weekday())
        if week_end > to_date:
            week_end = to_date

        # Sum daily totals for this week
        week_totals = _zero_macros()
        day = week_start
        while day <= week_end:
            if day in daily_totals:
                week_totals = _add_macros(week_totals, daily_totals[day])
            day += timedelta(days=1)

        # Use the target from the first day of the period for the week target
        target = targets_map.get(week_start)

        # Adherence: compare average daily calories to target
        num_days = (week_end - week_start).days + 1
        adherence = None
        if target is not None:
            avg_daily_calories = week_totals.calories / Decimal(str(num_days))
            adherence = avg_daily_calories <= Decimal(str(target.effective_calories))

        periods.append(
            PeriodTotals(
                period_start=week_start,
                period_end=week_end,
                totals=week_totals,
                effective_target=target,
                adherence=adherence,
            )
        )

        # Advance to next week
        current = week_end + timedelta(days=1)

    return periods


def _zero_macros() -> ItemMacros:
    """Return a zero-valued ItemMacros for summation."""

    return ItemMacros(
        calories=Decimal("0"),
        protein_g=Decimal("0"),
        carbs_g=Decimal("0"),
        fat_g=Decimal("0"),
        fiber_g=None,
        sat_fat_g=None,
        sodium_mg=None,
    )


def _add_macros(a: ItemMacros, b: ItemMacros) -> ItemMacros:
    """Sum two ItemMacros, treating None optional fields as 0 when the other is set."""

    def _add_opt(x: Decimal | None, y: Decimal | None) -> Decimal | None:
        if x is None and y is None:
            return None
        return (x or Decimal("0")) + (y or Decimal("0"))

    return ItemMacros(
        calories=a.calories + b.calories,
        protein_g=a.protein_g + b.protein_g,
        carbs_g=a.carbs_g + b.carbs_g,
        fat_g=a.fat_g + b.fat_g,
        fiber_g=_add_opt(a.fiber_g, b.fiber_g),
        sat_fat_g=_add_opt(a.sat_fat_g, b.sat_fat_g),
        sodium_mg=_add_opt(a.sodium_mg, b.sodium_mg),
    )
