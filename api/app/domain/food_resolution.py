"""Food resolution ladder used by log_meal and related write paths."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Food, Meal, MealItem
from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD, RECENT_LOOKBACK_DAYS
from app.domain.dto import FoodCandidate
from app.domain.errors import FoodAmbiguousError, FoodNotFoundError


def resolve_food(
    session: Session,
    *,
    food_id: int | None,
    name: str | None,
    has_supplied_macros: bool,
    now: datetime,
) -> Food | None:
    """Resolve a food using the section-4 ladder, escalating ambiguity.

    This function resolves food-backed items only; callers pass ad-hoc macros
    separately. Soft-deleted foods are never considered candidates.
    """

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    if food_id is not None:
        resolved = session.scalar(select(Food).where(Food.id == food_id, Food.deleted_at.is_(None)))
        if resolved is None:
            raise FoodNotFoundError(name or f"id:{food_id}")
        return resolved

    normalized_name = (name or "").strip()
    if not normalized_name:
        if has_supplied_macros:
            return None
        raise FoodNotFoundError("(missing name)")

    candidates = _find_food_candidates(session, normalized_name, now)
    if not candidates:
        if has_supplied_macros:
            return None
        raise FoodNotFoundError(normalized_name)

    if len(candidates) == 1:
        return session.get(Food, candidates[0].id)

    favorite_matches = [candidate for candidate in candidates if candidate.is_favorite]
    if len(favorite_matches) == 1:
        return session.get(Food, favorite_matches[0].id)

    if not favorite_matches:
        recent_matches = [
            candidate for candidate in candidates if candidate.last_logged_at is not None
        ]
        if len(recent_matches) == 1:
            return session.get(Food, recent_matches[0].id)

    raise FoodAmbiguousError(
        normalized_name,
        [_serialize_candidate(candidate) for candidate in candidates],
    )


def _find_food_candidates(session: Session, name: str, now: datetime) -> list[FoodCandidate]:
    query_name = name.strip().lower()
    exact_stmt = select(Food).where(
        Food.deleted_at.is_(None),
        func.lower(Food.name) == query_name,
    )
    exact_matches = list(session.scalars(exact_stmt))
    if exact_matches:
        return _hydrate_candidates(session, exact_matches, now)

    similarity_stmt = (
        select(Food)
        .where(
            Food.deleted_at.is_(None),
            func.similarity(func.lower(Food.name), query_name) >= FOOD_NAME_SIMILARITY_THRESHOLD,
        )
        .order_by(
            func.similarity(func.lower(Food.name), query_name).desc(),
            Food.name.asc(),
        )
        .limit(10)
    )

    has_trigram_similarity = session.scalar(select(func.to_regproc("similarity"))) is not None
    if has_trigram_similarity:
        fuzzy_matches = list(session.scalars(similarity_stmt))
    else:
        fallback_stmt = (
            select(Food)
            .where(Food.deleted_at.is_(None), func.lower(Food.name).contains(query_name))
            .order_by(Food.name.asc())
            .limit(10)
        )
        fuzzy_matches = list(session.scalars(fallback_stmt))

    return _hydrate_candidates(session, fuzzy_matches, now)


def _hydrate_candidates(session: Session, foods: list[Food], now: datetime) -> list[FoodCandidate]:
    if not foods:
        return []

    since = now.astimezone(UTC) - timedelta(days=RECENT_LOOKBACK_DAYS)
    last_seen_stmt = (
        select(MealItem.food_id, func.max(Meal.logged_at))
        .join(Meal, Meal.id == MealItem.meal_id)
        .where(
            MealItem.food_id.in_([food.id for food in foods]),
            Meal.logged_at >= since,
        )
        .group_by(MealItem.food_id)
    )
    last_seen_by_food_id = {
        int(food_id): logged_at
        for food_id, logged_at in session.execute(last_seen_stmt).all()
        if food_id is not None
    }

    candidates = [
        FoodCandidate(
            id=food.id,
            name=food.name,
            calories=food.calories,
            is_favorite=food.is_favorite,
            last_logged_at=last_seen_by_food_id.get(food.id),
        )
        for food in foods
    ]
    candidates.sort(key=lambda candidate: (candidate.name.lower(), candidate.id))
    return candidates


def _serialize_candidate(candidate: FoodCandidate) -> dict[str, object]:
    return {
        "id": candidate.id,
        "name": candidate.name,
        "calories": candidate.calories,
    }
