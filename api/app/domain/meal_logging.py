"""Meal logging and nutrition computation (T-023).

The log_meal function is the primary write path for logging meals. It resolves
items using the §4 ladder, materializes them with computed macros, and returns
the created meal with totals and delta vs. the effective target.
"""

from __future__ import annotations

from datetime import UTC, datetime, date
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Food, Meal, MealItem, MealItemSource, MealType, Target, IntervalsCaloriesOut
from app.domain.dto import (
    ItemMacros,
    MealItemSpec,
    MealItemResponse,
    MealResponse,
)
from app.domain.food_resolution import resolve_food
from app.domain.meal_timing import resolve_meal_type
from app.domain.nutrition_math import compute_item_macros


def log_meal(
    session: Session,
    *,
    items: list[MealItemSpec],
    logged_at: datetime,
    local_tz: str,
    meal_type: str | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> MealResponse:
    """Log a meal with resolved and computed items.

    Implements §4 item resolution: explicit food_id wins, then fuzzy name match,
    then favorite/recency tie-breaker, else ambiguity error. Ad-hoc items store
    macros; food-backed items compute them at read time.

    Returns the created meal with resolved items, totals, and delta vs. the
    effective target for that day.

    Args:
        session: Active SQLAlchemy session.
        items: List of item specs to resolve and log.
        logged_at: Timezone-aware timestamp (UTC) when the meal was eaten.
        local_tz: IANA timezone name (e.g. "Europe/Dublin").
        meal_type: Optional override (breakfast/lunch/dinner/snack).
        notes: Optional meal notes.
        now: Timezone-aware "now" for date parsing (defaults to UTC now).

    Returns:
        MealResponse with created meal, resolved items, totals, and delta.

    Raises:
        ValueError: If logged_at is not timezone-aware.
        FoodNotFoundError: If an item cannot be resolved and no macros supplied.
        FoodAmbiguousError: If an item matches multiple foods without a tie-breaker.
    """

    if logged_at.tzinfo is None:
        raise ValueError("logged_at must be timezone-aware")

    # Derive local_date from logged_at in the meal's timezone
    local_dt = logged_at.astimezone(ZoneInfo(local_tz))
    local_date = local_dt.date()

    # Resolve meal type from inference or override
    meal_type_enum = resolve_meal_type(
        MealType(meal_type) if meal_type else None,
        logged_at,
        local_tz,
    )

    # Resolve and prepare each item
    resolved_items: list[tuple[MealItemSpec, MealItem]] = []
    for spec in items:
        has_supplied_macros = any(
            getattr(spec, field) is not None
            for field in ["calories", "protein_g", "carbs_g", "fat_g"]
        )

        # Resolution ladder (§4)
        resolved_food = resolve_food(
            session,
            food_id=spec.food_id,
            name=spec.name,
            has_supplied_macros=has_supplied_macros,
            now=now or datetime.now(UTC),
        )

        # Determine source and create meal_item
        if resolved_food is not None:
            source = MealItemSource.label  # Default to label source
            item_name = resolved_food.name
            item_food_id = resolved_food.id
            # Food-backed items don't store macros (§6)
            meal_item = MealItem(
                name=item_name,
                food_id=item_food_id,
                quantity=spec.quantity,
                quantity_unit=spec.quantity_unit,
                source=source,
            )
        else:
            # Ad-hoc item: store the provided macros
            source = MealItemSource.estimate
            meal_item = MealItem(
                name=spec.name,
                food_id=None,
                quantity=spec.quantity,
                quantity_unit=spec.quantity_unit,
                calories=spec.calories,
                protein_g=spec.protein_g,
                carbs_g=spec.carbs_g,
                fat_g=spec.fat_g,
                fiber_g=spec.fiber_g,
                sat_fat_g=spec.sat_fat_g,
                sodium_mg=spec.sodium_mg,
                source=source,
            )

        resolved_items.append((spec, meal_item))

    # Create the meal in a transaction
    meal = Meal(
        logged_at=logged_at,
        local_tz=local_tz,
        local_date=local_date,
        meal_type=meal_type_enum,
        notes=notes,
    )
    session.add(meal)
    session.flush()  # Populate meal.id

    # Add items to the meal
    for spec, meal_item in resolved_items:
        meal_item.meal_id = meal.id
        session.add(meal_item)

    session.flush()  # Ensure all items have ids

    # Compute totals
    totals = _compute_meal_totals(session, meal, resolved_items)

    # Compute delta vs. effective target
    delta = _compute_delta_vs_target(session, totals, local_date)

    # Build response with resolved items
    item_responses = []
    for i, (spec, meal_item) in enumerate(resolved_items):
        # Reload the item to get the computed macros
        refreshed_item = session.get(MealItem, meal_item.id)
        
        # For food-backed items, load the food; for ad-hoc items, pass None
        food = None
        if refreshed_item.food_id is not None:
            food = session.get(Food, refreshed_item.food_id)
        
        macros = compute_item_macros(refreshed_item, food)

        item_responses.append(
            MealItemResponse(
                id=refreshed_item.id,
                food_id=refreshed_item.food_id,
                name=refreshed_item.name,
                quantity=refreshed_item.quantity,
                quantity_unit=refreshed_item.quantity_unit,
                source=refreshed_item.source,
                macros=macros,
            )
        )

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


def _compute_meal_totals(
    session: Session,
    meal: Meal,
    resolved_items: list[tuple[MealItemSpec, MealItem]],
) -> ItemMacros:
    """Sum all item macros for the meal."""

    total_calories = Decimal("0")
    total_protein_g = Decimal("0")
    total_carbs_g = Decimal("0")
    total_fat_g = Decimal("0")
    total_fiber_g = Decimal("0")
    total_sat_fat_g = Decimal("0")
    total_sodium_mg = Decimal("0")

    for spec, meal_item in resolved_items:
        # Reload item to ensure it has the ID
        refreshed_item = session.get(MealItem, meal_item.id)
        
        # For food-backed items, load the food; for ad-hoc items, pass None
        food = None
        if refreshed_item.food_id is not None:
            food = session.get(Food, refreshed_item.food_id)
        
        macros = compute_item_macros(refreshed_item, food)
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

    return ItemMacros(
        calories=total_calories,
        protein_g=total_protein_g,
        carbs_g=total_carbs_g,
        fat_g=total_fat_g,
        fiber_g=total_fiber_g if total_fiber_g else None,
        sat_fat_g=total_sat_fat_g if total_sat_fat_g else None,
        sodium_mg=total_sodium_mg if total_sodium_mg else None,
    )


def _compute_delta_vs_target(
    session: Session,
    meal_totals: ItemMacros,
    local_date: date,
) -> ItemMacros | None:
    """Compute the difference between meal totals and effective target.

    Returns None if no target is set for the date.
    """

    # Get the effective target for this date
    target_stmt = (
        select(Target)
        .where(Target.effective_from <= local_date)
        .order_by(Target.effective_from.desc())
        .limit(1)
    )
    target = session.scalar(target_stmt)

    if target is None:
        return None

    # Get any cached calories_out for the date
    cached_out = session.scalar(
        select(IntervalsCaloriesOut).where(IntervalsCaloriesOut.date == local_date)
    )

    # Compute effective target
    total_calories_target = Decimal(str(target.base_calories))
    if cached_out is not None:
        total_calories_target += Decimal(str(cached_out.calories_out))

    # Delta is (meal - target), so positive means over target
    return ItemMacros(
        calories=meal_totals.calories - total_calories_target,
        protein_g=meal_totals.protein_g - Decimal(str(target.protein_g)),
        carbs_g=meal_totals.carbs_g - Decimal(str(target.carbs_g)),
        fat_g=meal_totals.fat_g - Decimal(str(target.fat_g)),
        fiber_g=meal_totals.fiber_g,  # No target for micros
        sat_fat_g=meal_totals.sat_fat_g,
        sodium_mg=meal_totals.sodium_mg,
    )
