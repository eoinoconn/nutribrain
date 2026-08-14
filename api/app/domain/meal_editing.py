"""update_meal and update_meal_item: single-field correction path (MCP-01).

Every correction used to be delete_meal + a full log_meal re-emission, which is
both token-wasteful and a source of ghost meals from a forgotten or racing
delete. These two functions let a caller fix one field in place instead.

update_meal mutates the Meal row only (meal_type, logged_at, notes) — it never
touches items. update_meal_item mutates one meal_item's own fields (quantity,
quantity_unit, food_id, and — for ad-hoc items only — macros). Neither adds or
removes items from a meal; that is delete_meal_item + a fresh log_meal item.

Per the mutation rules, meal_item.quantity and meal_item.food_id edits are
local to that one meal_item — they never rewrite history the way update_food
does. Food-linked items (food_id IS NOT NULL) always compute macros live and
must keep macros NULL in storage (the ``adhoc_macros`` CHECK); attempting to
edit macros on a food-linked item is rejected rather than silently dropped.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import Food, IntervalsCaloriesOut, Meal, MealItem, MealType, QuantityUnit, Target
from app.domain.dto import ItemMacros, MealItemResponse, MealResponse
from app.domain.errors import (
    FoodNotFoundError,
    MealItemFoodLinkedError,
    MealItemMacrosRequiredError,
    MealItemNotFoundError,
    MealNotFoundError,
)
from app.domain.nutrition_math import compute_item_macros
from app.logging import get_logger

logger = get_logger(__name__)

# Sentinel for distinguishing "not passed" from "explicitly passed None",
# same pattern as update_food.
_SENTINEL: object = object()

_REQUIRED_MACRO_FIELDS = ("calories", "protein_g", "carbs_g", "fat_g")


def update_meal(
    session: Session,
    *,
    meal_id: int,
    meal_type: MealType | str | None = None,
    logged_at: datetime | None = None,
    notes: str | None = _SENTINEL,  # type: ignore[assignment]
) -> MealResponse:
    """Partial update of a meal's own fields. Never adds, removes, or edits items.

    ``meal_type`` and ``logged_at`` are simple non-nullable overrides — omit to
    leave unchanged. ``notes`` follows the explicit-clear sentinel pattern:
    omit to leave unchanged, pass ``None`` to clear it.

    Changing ``logged_at`` re-derives ``local_date`` from the meal's existing
    ``local_tz`` (this function does not accept a new timezone). ``meal_type``
    is not re-inferred when only ``logged_at`` changes — pass it explicitly if
    the new time falls in a different meal-type window.

    Returns the meal with its items, totals, and delta vs. target recomputed
    at read time (unaffected by this call, since items are untouched).
    """

    meal = session.get(Meal, meal_id)
    if meal is None:
        raise MealNotFoundError(meal_id)

    if logged_at is not None:
        if logged_at.tzinfo is None:
            raise ValueError("logged_at must be timezone-aware")
        meal.logged_at = logged_at
        local_dt = logged_at.astimezone(ZoneInfo(meal.local_tz))
        meal.local_date = local_dt.date()

    if meal_type is not None:
        meal.meal_type = MealType(meal_type) if isinstance(meal_type, str) else meal_type

    if notes is not _SENTINEL:
        meal.notes = notes

    session.flush()
    logger.info("meal_updated", meal_id=meal_id)
    return _build_meal_response(session, meal)


def update_meal_item(
    session: Session,
    *,
    item_id: int,
    quantity: Decimal | None = None,
    quantity_unit: QuantityUnit | None = None,
    food_id: int | None = _SENTINEL,  # type: ignore[assignment]
    calories: Decimal | None = None,
    protein_g: Decimal | None = None,
    carbs_g: Decimal | None = None,
    fat_g: Decimal | None = None,
    fiber_g: Decimal | None = _SENTINEL,  # type: ignore[assignment]
    sat_fat_g: Decimal | None = _SENTINEL,  # type: ignore[assignment]
    sodium_mg: Decimal | None = _SENTINEL,  # type: ignore[assignment]
) -> MealItemResponse:
    """Partial update of one meal_item. Local to that item only; never touches siblings.

    ``quantity`` and ``quantity_unit`` are simple overrides — you ate what you
    ate that day, so this never rewrites other meals.

    ``food_id`` swaps the food a food-linked item resolves against, or moves
    the item between food-linked and ad-hoc:
    - Passed and the item stays food-linked (old and new food_id both non-null,
      or unset and already food-linked): macro fields must not be supplied —
      food-linked items always compute macros live and stay NULL in storage.
      Raises ``MealItemFoodLinkedError`` if any macro field is passed.
    - Passed as ``None`` while currently food-linked: the item becomes ad-hoc.
      ``calories``, ``protein_g``, ``carbs_g``, and ``fat_g`` become required in
      this same call (mirroring the ``adhoc_macros`` CHECK) — raises
      ``MealItemMacrosRequiredError`` if any is missing. ``fiber_g``,
      ``sat_fat_g``, ``sodium_mg`` are optional.
    - Passed as a food id while currently ad-hoc (or omitted while already
      food-linked): resolves the target food (``FoodNotFoundError`` if it does
      not exist or is soft-deleted) and clears any stored macros to NULL.

    If ``food_id`` is omitted and the item is already ad-hoc, macro fields are
    a normal partial update: ``calories``/``protein_g``/``carbs_g``/``fat_g``
    are required-but-non-clearable (pass a value to change it, omit to leave
    it), and ``fiber_g``/``sat_fat_g``/``sodium_mg`` follow the explicit-clear
    sentinel pattern.
    """

    item = session.get(MealItem, item_id)
    if item is None:
        raise MealItemNotFoundError(item_id)

    food_id_changing = food_id is not _SENTINEL
    target_food_id = food_id if food_id_changing else item.food_id

    macro_fields_supplied = (
        calories is not None
        or protein_g is not None
        or carbs_g is not None
        or fat_g is not None
        or fiber_g is not _SENTINEL
        or sat_fat_g is not _SENTINEL
        or sodium_mg is not _SENTINEL
    )

    if target_food_id is not None:
        # Staying (or becoming) food-linked: macros must remain NULL.
        if macro_fields_supplied:
            raise MealItemFoodLinkedError(item_id)

        if food_id_changing:
            food = session.scalar(
                select(Food).where(Food.id == target_food_id, Food.deleted_at.is_(None))
            )
            if food is None:
                raise FoodNotFoundError(f"id:{target_food_id}")
            item.food_id = target_food_id
            item.calories = None
            item.protein_g = None
            item.carbs_g = None
            item.fat_g = None
            item.fiber_g = None
            item.sat_fat_g = None
            item.sodium_mg = None
    elif food_id_changing and item.food_id is not None:
        # Transition: food-linked -> ad-hoc. Required macros must be supplied now.
        missing = [
            field_name
            for field_name, value in (
                ("calories", calories),
                ("protein_g", protein_g),
                ("carbs_g", carbs_g),
                ("fat_g", fat_g),
            )
            if value is None
        ]
        if missing:
            raise MealItemMacrosRequiredError(item_id, missing)

        item.food_id = None
        item.calories = calories
        item.protein_g = protein_g
        item.carbs_g = carbs_g
        item.fat_g = fat_g
        item.fiber_g = fiber_g if fiber_g is not _SENTINEL else None
        item.sat_fat_g = sat_fat_g if sat_fat_g is not _SENTINEL else None
        item.sodium_mg = sodium_mg if sodium_mg is not _SENTINEL else None
    else:
        # Already ad-hoc and staying ad-hoc: ordinary partial update.
        if calories is not None:
            item.calories = calories
        if protein_g is not None:
            item.protein_g = protein_g
        if carbs_g is not None:
            item.carbs_g = carbs_g
        if fat_g is not None:
            item.fat_g = fat_g
        if fiber_g is not _SENTINEL:
            item.fiber_g = fiber_g
        if sat_fat_g is not _SENTINEL:
            item.sat_fat_g = sat_fat_g
        if sodium_mg is not _SENTINEL:
            item.sodium_mg = sodium_mg

    if quantity is not None:
        item.quantity = quantity
    if quantity_unit is not None:
        item.quantity_unit = quantity_unit

    session.flush()
    logger.info("meal_item_updated", item_id=item_id, meal_id=item.meal_id)
    return _build_item_response(session, item)


# --- Internal helpers -------------------------------------------------------


def _build_item_response(session: Session, item: MealItem) -> MealItemResponse:
    """Build a MealItemResponse for one item, computing macros at read time."""

    food = session.get(Food, item.food_id) if item.food_id is not None else None
    macros = compute_item_macros(item, food)
    return MealItemResponse(
        id=item.id,
        food_id=item.food_id,
        name=item.name,
        quantity=item.quantity,
        quantity_unit=item.quantity_unit,
        source=item.source,
        macros=macros,
    )


def _build_meal_response(session: Session, meal: Meal) -> MealResponse:
    """Build a MealResponse with items, totals, and delta computed at read time."""

    stmt = select(MealItem).where(MealItem.meal_id == meal.id).options(selectinload(MealItem.food))
    items = list(session.scalars(stmt))

    item_responses: list[MealItemResponse] = []
    total_calories = Decimal("0")
    total_protein_g = Decimal("0")
    total_carbs_g = Decimal("0")
    total_fat_g = Decimal("0")
    total_fiber_g = Decimal("0")
    total_sat_fat_g = Decimal("0")
    total_sodium_mg = Decimal("0")

    for item in items:
        macros = compute_item_macros(item, item.food)
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
                id=item.id,
                food_id=item.food_id,
                name=item.name,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                source=item.source,
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

    delta = _compute_delta_vs_target(session, totals, meal.local_date)

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
