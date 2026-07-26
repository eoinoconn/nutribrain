"""Foods domain operations: add, update, set_favorite, soft-delete.

Food edits propagate to past meals at read time (no writes needed). Editing
serving_unit is forbidden — the correct action is to create a new food.
"""

from __future__ import annotations

# --- DTOs ------------------------------------------------------------------
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import Food, Meal, MealItem, ServingUnit
from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD
from app.domain.errors import (
    FoodDuplicateError,
    FoodNotFoundError,
    ServingUnitImmutableError,
)
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AddFoodResult:
    food: Food


@dataclass(frozen=True, slots=True)
class UpdateFoodResult:
    food: Food
    affected_meals_count: int


@dataclass(frozen=True, slots=True)
class FoodSearchResult:
    food: Food
    last_logged_at: datetime | None
    logged_count: int


# Sentinel for distinguishing "not passed" from "explicitly passed None"
_SENTINEL: object = object()


# --- Public operations -----------------------------------------------------


def add_food(
    session: Session,
    *,
    name: str,
    serving_size: Decimal,
    serving_unit: ServingUnit,
    calories: Decimal,
    protein_g: Decimal,
    carbs_g: Decimal,
    fat_g: Decimal,
    fiber_g: Decimal | None = None,
    sat_fat_g: Decimal | None = None,
    sodium_mg: Decimal | None = None,
    density_g_per_ml: Decimal | None = None,
    force: bool = False,
) -> AddFoodResult:
    """Create a food, raising food_duplicate on fuzzy name collision unless force.

    Duplicate detection uses pg_trgm similarity when available, falling back to
    case-insensitive substring matching (same logic as food resolution).
    """

    if not force:
        duplicates = _find_duplicates(session, name)
        if duplicates:
            raise FoodDuplicateError(
                name,
                [{"id": f.id, "name": f.name, "calories": f.calories} for f in duplicates],
            )

    food = Food(
        name=name.strip(),
        serving_size=serving_size,
        serving_unit=serving_unit,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        sat_fat_g=sat_fat_g,
        sodium_mg=sodium_mg,
        density_g_per_ml=density_g_per_ml,
    )
    session.add(food)
    session.flush()
    logger.info("food_added", food_id=food.id, name=food.name)
    return AddFoodResult(food=food)


def update_food(
    session: Session,
    *,
    food_id: int,
    name: str | None = None,
    serving_size: Decimal | None = None,
    serving_unit: ServingUnit | None = None,
    calories: Decimal | None = None,
    protein_g: Decimal | None = None,
    carbs_g: Decimal | None = None,
    fat_g: Decimal | None = None,
    fiber_g: Decimal | None = _SENTINEL,  # type: ignore[assignment]
    sat_fat_g: Decimal | None = _SENTINEL,  # type: ignore[assignment]
    sodium_mg: Decimal | None = _SENTINEL,  # type: ignore[assignment]
    density_g_per_ml: Decimal | None = _SENTINEL,  # type: ignore[assignment]
) -> UpdateFoodResult:
    """Partial update of a food. Rejects serving_unit changes.

    Returns the updated food and a count of past meals whose items reference
    this food (and will therefore recompute at read time).
    """

    if serving_unit is not None:
        raise ServingUnitImmutableError()

    food = session.scalar(select(Food).where(Food.id == food_id, Food.deleted_at.is_(None)))
    if food is None:
        raise FoodNotFoundError(f"id:{food_id}")

    if name is not None:
        food.name = name.strip()
    if serving_size is not None:
        food.serving_size = serving_size
    if calories is not None:
        food.calories = calories
    if protein_g is not None:
        food.protein_g = protein_g
    if carbs_g is not None:
        food.carbs_g = carbs_g
    if fat_g is not None:
        food.fat_g = fat_g
    if fiber_g is not _SENTINEL:
        food.fiber_g = fiber_g
    if sat_fat_g is not _SENTINEL:
        food.sat_fat_g = sat_fat_g
    if sodium_mg is not _SENTINEL:
        food.sodium_mg = sodium_mg
    if density_g_per_ml is not _SENTINEL:
        food.density_g_per_ml = density_g_per_ml

    session.flush()

    affected_meals_count = _count_affected_meals(session, food_id)
    logger.info("food_updated", food_id=food_id, affected_meals_count=affected_meals_count)
    return UpdateFoodResult(food=food, affected_meals_count=affected_meals_count)


def set_favorite_food(
    session: Session,
    *,
    food_id: int,
    is_favorite: bool,
) -> Food:
    """Toggle favorite status for disambiguation resolution."""

    food = session.scalar(select(Food).where(Food.id == food_id, Food.deleted_at.is_(None)))
    if food is None:
        raise FoodNotFoundError(f"id:{food_id}")

    food.is_favorite = is_favorite
    session.flush()
    return food


def delete_food(
    session: Session,
    *,
    food_id: int,
    now: datetime | None = None,
) -> Food:
    """Soft-delete a food. Past meal_items still reference it for history."""

    food = session.scalar(select(Food).where(Food.id == food_id, Food.deleted_at.is_(None)))
    if food is None:
        raise FoodNotFoundError(f"id:{food_id}")

    if now is None:
        now = datetime.now(UTC)
    food.deleted_at = now
    session.flush()
    logger.info("food_deleted", food_id=food_id)
    return food


def search_foods(
    session: Session,
    *,
    query: str,
    limit: int = 20,
) -> list[FoodSearchResult]:
    """Search non-deleted foods by fuzzy name with usage metadata.

    Returns favorite marker + ``last_logged_at``/``logged_count`` (G3) for each
    candidate. The usage stats are computed in-query, never stored.
    """

    lowered_query = query.strip().lower()
    stats_subquery = (
        select(
            MealItem.food_id.label("food_id"),
            func.max(Meal.logged_at).label("last_logged_at"),
            func.count(MealItem.id).label("logged_count"),
        )
        .join(Meal, Meal.id == MealItem.meal_id)
        .where(MealItem.food_id.is_not(None))
        .group_by(MealItem.food_id)
        .subquery()
    )

    stmt = (
        select(
            Food,
            stats_subquery.c.last_logged_at,
            func.coalesce(stats_subquery.c.logged_count, 0).label("logged_count"),
        )
        .outerjoin(stats_subquery, stats_subquery.c.food_id == Food.id)
        .where(Food.deleted_at.is_(None))
    )

    if lowered_query:
        exact_match = func.lower(Food.name) == lowered_query
        has_trigram_similarity = session.scalar(select(func.to_regproc("similarity"))) is not None
        if has_trigram_similarity:
            similarity = func.similarity(func.lower(Food.name), lowered_query)
            stmt = (
                stmt.where(
                    exact_match
                    | (similarity >= FOOD_NAME_SIMILARITY_THRESHOLD)
                    | func.lower(Food.name).contains(lowered_query)
                )
                .order_by(
                    case((exact_match, 1), else_=0).desc(),
                    similarity.desc(),
                    Food.is_favorite.desc(),
                    Food.name.asc(),
                )
                .limit(limit)
            )
        else:
            stmt = (
                stmt.where(exact_match | func.lower(Food.name).contains(lowered_query))
                .order_by(
                    case((exact_match, 1), else_=0).desc(),
                    Food.is_favorite.desc(),
                    Food.name.asc(),
                )
                .limit(limit)
            )
    else:
        stmt = stmt.order_by(Food.is_favorite.desc(), Food.name.asc()).limit(limit)

    rows = session.execute(stmt).all()
    return [
        FoodSearchResult(
            food=row[0],
            last_logged_at=row[1],
            logged_count=int(row[2]),
        )
        for row in rows
    ]


# --- Internal helpers -------------------------------------------------------


def _find_duplicates(session: Session, name: str) -> list[Food]:
    """Find existing non-deleted foods with similar names."""

    query_name = name.strip().lower()

    # Exact match first
    exact_stmt = select(Food).where(
        Food.deleted_at.is_(None),
        func.lower(Food.name) == query_name,
    )
    exact_matches = list(session.scalars(exact_stmt))
    if exact_matches:
        return exact_matches

    # Fuzzy match via pg_trgm if available
    has_trigram = session.scalar(select(func.to_regproc("similarity"))) is not None
    if has_trigram:
        fuzzy_stmt = (
            select(Food)
            .where(
                Food.deleted_at.is_(None),
                func.similarity(func.lower(Food.name), query_name)
                >= FOOD_NAME_SIMILARITY_THRESHOLD,
            )
            .order_by(func.similarity(func.lower(Food.name), query_name).desc())
            .limit(5)
        )
        return list(session.scalars(fuzzy_stmt))

    # Fallback: substring match
    fallback_stmt = (
        select(Food)
        .where(Food.deleted_at.is_(None), func.lower(Food.name).contains(query_name))
        .order_by(Food.name.asc())
        .limit(5)
    )
    return list(session.scalars(fallback_stmt))


def _count_affected_meals(session: Session, food_id: int) -> int:
    """Count distinct meals that have items referencing this food."""

    stmt = select(func.count(func.distinct(MealItem.meal_id))).where(MealItem.food_id == food_id)
    result = session.scalar(stmt)
    return int(result) if result else 0
