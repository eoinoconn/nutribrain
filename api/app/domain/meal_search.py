"""find_meal: fuzzy search over logged meal items (MCP-03).

"When did I last have X" used to mean walking ``get_day`` one day at a time.
``find_meal`` searches ``meal_items.name`` directly instead of joining
``foods``: ``log_meal``/``copy_meal``/``log_template`` all snapshot the
resolved food's name (or the ad-hoc name) onto ``meal_items.name`` at write
time, so every row already carries a meaningful searchable name whether or
not ``food_id`` is set. A join to ``foods`` would only be needed to search by
a food's *current* name after a cosmetic rename, which is out of scope here.

Matching reuses the same fuzzy approach as ``search_foods`` (§ app.domain.foods):
exact match, trigram similarity above ``FOOD_NAME_SIMILARITY_THRESHOLD``, and a
plain substring-contains fallback for environments without ``pg_trgm``.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import case, select
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session, selectinload

from app.db import Meal, MealItem
from app.domain.constants import FOOD_NAME_SIMILARITY_THRESHOLD
from app.domain.dto import MealItemMatch
from app.domain.nutrition_math import compute_item_macros

DEFAULT_FIND_MEAL_LIMIT = 20


def find_meal(
    session: Session,
    *,
    query: str,
    since: date | None = None,
    limit: int = DEFAULT_FIND_MEAL_LIMIT,
) -> list[MealItemMatch]:
    """Search logged meal items by name, most-recent-first.

    Matches against ``meal_items.name``, which is populated for both
    food-linked items (snapshotted from the resolved food's name at log time)
    and ad-hoc items (the name supplied by the caller) — no join to ``foods``
    is needed.

    Args:
        session: Active SQLAlchemy session.
        query: Free-text name to fuzzy-match, case-insensitive.
        since: Optional lower bound (inclusive) on ``local_date``.
        limit: Max number of results to return (default 20).

    Returns:
        Matching items ordered by ``logged_at`` descending, each carrying
        ``meal_id``/``item_id`` plus quantity and read-time-computed macros
        so a result can feed directly into ``copy_meal`` or
        ``update_meal_item`` without another round-trip. Returns an empty
        list when nothing matches — never raises for "no results".
    """

    lowered_query = query.strip().lower()

    stmt = (
        select(MealItem, Meal.logged_at, Meal.local_date)
        .join(Meal, Meal.id == MealItem.meal_id)
        .options(selectinload(MealItem.food))
    )

    if since is not None:
        stmt = stmt.where(Meal.local_date >= since)

    order_by_clauses = [Meal.logged_at.desc()]

    if lowered_query:
        exact_match = sa_func.lower(MealItem.name) == lowered_query
        has_trigram_similarity = (
            session.scalar(select(sa_func.to_regproc("similarity"))) is not None
        )
        if has_trigram_similarity:
            similarity = sa_func.similarity(sa_func.lower(MealItem.name), lowered_query)
            stmt = stmt.where(
                exact_match
                | (similarity >= FOOD_NAME_SIMILARITY_THRESHOLD)
                | sa_func.lower(MealItem.name).contains(lowered_query)
            )
            order_by_clauses = [
                case((exact_match, 1), else_=0).desc(),
                similarity.desc(),
                Meal.logged_at.desc(),
            ]
        else:
            stmt = stmt.where(sa_func.lower(MealItem.name).contains(lowered_query))

    stmt = stmt.order_by(*order_by_clauses).limit(limit)

    rows = session.execute(stmt).unique().all()

    return [
        MealItemMatch(
            meal_id=item.meal_id,
            item_id=item.id,
            food_id=item.food_id,
            logged_at=logged_at,
            local_date=local_date,
            name=item.name,
            quantity=item.quantity,
            quantity_unit=item.quantity_unit,
            macros=compute_item_macros(item, item.food),
        )
        for item, logged_at, local_date in rows
    ]
