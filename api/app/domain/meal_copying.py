"""copy_meal: re-materialize an existing meal's items into a new meal (MCP-02).

"Same as yesterday" used to cost a full ``get_day`` round trip (fetch the whole
day, parse it client-side, then re-emit every item through ``log_meal``).
``copy_meal`` reads one source meal's items directly and re-materializes them
as a new meal, the same shape as :func:`app.domain.templates.log_template`'s
template -> meal materialization:

- food_id set on the source item -> the new item gets the same food_id; macros
  stay live-computed (never snapshotted).
- food_id NULL (ad-hoc) on the source item -> its stored macro snapshot is
  copied onto the new item.
- ``quantity_scale`` multiplies every item's quantity uniformly (defaults to 1
  when omitted, mirroring ``log_template``).
- each new item's ``source`` (label/template/estimate/manual) carries forward
  from the item it was copied from — there is no distinct "copy" provenance
  value in the schema, so the original provenance is preserved instead.

The source meal itself is never modified.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import Food, IntervalsCaloriesOut, Meal, MealItem, MealType, Target
from app.domain.dto import ItemMacros, MealItemResponse, MealResponse
from app.domain.errors import MealNotFoundError
from app.domain.meal_timing import parse_local_date, resolve_meal_type
from app.domain.nutrition_math import compute_item_macros
from app.logging import get_logger

logger = get_logger(__name__)


def copy_meal(
    session: Session,
    *,
    meal_id: int,
    local_tz: str,
    to_day: str | date | None = None,
    at: time | None = None,
    meal_type: MealType | None = None,
    quantity_scale: Decimal | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> MealResponse:
    """Copy an existing meal's items into a new meal.

    Items are re-materialized exactly like ``log_template``'s template -> meal
    step: food-linked items carry ``food_id`` forward (macros stay
    live-computed, never snapshotted); ad-hoc items copy their stored macro
    snapshot. ``quantity_scale`` multiplies every item's quantity uniformly
    and defaults to 1 when omitted, matching ``log_template``.

    ``to_day`` accepts a date token (``today``/``yesterday``) or an ISO date,
    resolved in ``local_tz``; it defaults to ``today``. ``at`` sets the
    time-of-day within that resolved day; when omitted, the source meal's own
    local time-of-day is reused (so a copy defaults to "same time, different
    day" rather than "right now"), converted into ``local_tz``'s wall clock.

    ``meal_type`` is re-inferred from the new ``logged_at``/``local_tz`` (the
    same time-window inference ``log_meal`` uses) when omitted, rather than
    carried forward from the source meal — a breakfast copied to 19:00
    becomes a dinner, matching what a fresh ``log_meal`` call at that time
    would infer. Pass ``meal_type`` explicitly to override the inference.

    ``notes`` is NOT copied from the source meal: a copied meal is a new
    event, and yesterday's specific note (e.g. "big appetite today") should
    not silently land on today's copy. Omit ``notes`` to leave the new meal's
    notes empty; pass it explicitly to set one.

    Raises:
        MealNotFoundError: If no meal exists with ``meal_id``.
    """

    source = _get_meal_or_raise(session, meal_id)

    local_day = parse_local_date(to_day if to_day is not None else "today", local_tz, now=now)

    if at is not None:
        local_time = at
    else:
        source_local_dt = source.logged_at.astimezone(ZoneInfo(source.local_tz))
        local_time = source_local_dt.timetz().replace(tzinfo=None)

    local_dt = datetime.combine(local_day, local_time, tzinfo=ZoneInfo(local_tz))
    logged_at = local_dt.astimezone(UTC)

    resolved_meal_type = resolve_meal_type(meal_type, logged_at, local_tz)

    scale = quantity_scale if quantity_scale is not None else Decimal("1")

    meal = Meal(
        logged_at=logged_at,
        local_tz=local_tz,
        local_date=local_day,
        meal_type=resolved_meal_type,
        notes=notes,
    )
    session.add(meal)
    session.flush()

    meal_items: list[MealItem] = []
    for src_item in source.items:
        scaled_quantity = src_item.quantity * scale

        if src_item.food_id is not None:
            mi = MealItem(
                meal_id=meal.id,
                food_id=src_item.food_id,
                name=src_item.name,
                quantity=scaled_quantity,
                quantity_unit=src_item.quantity_unit,
                source=src_item.source,
            )
        else:
            mi = MealItem(
                meal_id=meal.id,
                food_id=None,
                name=src_item.name,
                quantity=scaled_quantity,
                quantity_unit=src_item.quantity_unit,
                calories=_scale_macro(src_item.calories, scale),
                protein_g=_scale_macro(src_item.protein_g, scale),
                carbs_g=_scale_macro(src_item.carbs_g, scale),
                fat_g=_scale_macro(src_item.fat_g, scale),
                fiber_g=_scale_macro(src_item.fiber_g, scale),
                sat_fat_g=_scale_macro(src_item.sat_fat_g, scale),
                sodium_mg=_scale_macro(src_item.sodium_mg, scale),
                source=src_item.source,
            )
        session.add(mi)
        meal_items.append(mi)

    session.flush()
    logger.info("meal_copied", source_meal_id=meal_id, meal_id=meal.id, item_count=len(meal_items))

    total_calories = Decimal("0")
    total_protein_g = Decimal("0")
    total_carbs_g = Decimal("0")
    total_fat_g = Decimal("0")
    total_fiber_g = Decimal("0")
    total_sat_fat_g = Decimal("0")
    total_sodium_mg = Decimal("0")

    item_responses: list[MealItemResponse] = []
    for mi in meal_items:
        food: Food | None = None
        if mi.food_id is not None:
            food = session.get(Food, mi.food_id)
        macros = compute_item_macros(mi, food)

        total_calories += macros.calories
        total_protein_g += macros.protein_g
        total_carbs_g += macros.carbs_g
        total_fat_g += macros.fat_g
        if macros.fiber_g is not None:
            total_fiber_g += macros.fiber_g
        if macros.sat_fat_g is not None:
            total_sat_fat_g += macros.sat_fat_g
        if macros.sodium_mg is not None:
            total_sodium_mg += macros.sodium_mg

        item_responses.append(
            MealItemResponse(
                id=mi.id,
                food_id=mi.food_id,
                name=mi.name,
                quantity=mi.quantity,
                quantity_unit=mi.quantity_unit,
                source=mi.source,
                macros=macros,
            )
        )

    totals = ItemMacros(
        calories=total_calories,
        protein_g=total_protein_g,
        carbs_g=total_carbs_g,
        fat_g=total_fat_g,
        fiber_g=total_fiber_g if total_fiber_g else None,
        sat_fat_g=total_sat_fat_g if total_sat_fat_g else None,
        sodium_mg=total_sodium_mg if total_sodium_mg else None,
    )

    delta = _compute_delta_vs_target(session, totals, local_day)

    return MealResponse(
        id=meal.id,
        logged_at=meal.logged_at,
        local_tz=meal.local_tz,
        local_date=meal.local_date,
        meal_type=meal.meal_type,
        notes=meal.notes,
        items=item_responses,
        totals=totals,
        delta_vs_target=delta,
    )


# --- Private helpers --------------------------------------------------------


def _get_meal_or_raise(session: Session, meal_id: int) -> Meal:
    """Load a meal with its items or raise MealNotFoundError.

    Meals are hard-deleted (no soft-delete marker), so a missing row simply
    means not found — mirrors the pattern in ``meal_deletion.delete_meal``.
    """

    stmt = select(Meal).where(Meal.id == meal_id).options(selectinload(Meal.items))
    meal = session.scalar(stmt)
    if meal is None:
        raise MealNotFoundError(meal_id)
    return meal


def _scale_macro(value: Decimal | None, scale: Decimal) -> Decimal | None:
    """Scale a macro value by quantity_scale, preserving None."""

    if value is None:
        return None
    return value * scale


def _compute_delta_vs_target(
    session: Session,
    meal_totals: ItemMacros,
    local_date: date,
) -> ItemMacros | None:
    """Compute the difference between meal totals and effective target.

    Returns None if no target is set for the date. Mirrors
    meal_logging._compute_delta_vs_target.
    """

    target_stmt = (
        select(Target)
        .where(Target.effective_from <= local_date)
        .order_by(Target.effective_from.desc())
        .limit(1)
    )
    target = session.scalar(target_stmt)

    if target is None:
        return None

    cached_out = session.scalar(
        select(IntervalsCaloriesOut).where(IntervalsCaloriesOut.date == local_date)
    )

    total_calories_target = Decimal(str(target.base_calories))
    if cached_out is not None:
        total_calories_target += Decimal(str(cached_out.calories_out))

    return ItemMacros(
        calories=meal_totals.calories - total_calories_target,
        protein_g=meal_totals.protein_g - Decimal(str(target.protein_g)),
        carbs_g=meal_totals.carbs_g - Decimal(str(target.carbs_g)),
        fat_g=meal_totals.fat_g - Decimal(str(target.fat_g)),
        fiber_g=meal_totals.fiber_g,
        sat_fat_g=meal_totals.sat_fat_g,
        sodium_mg=meal_totals.sodium_mg,
    )
