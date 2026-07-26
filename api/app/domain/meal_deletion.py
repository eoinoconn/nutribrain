"""Hard-delete operations for meals and meal items (T-028).

Per spec §3 deletion semantics, meals and meal_items are hard-deleted.
Undo is "log it again."
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import Meal, MealItem
from app.domain.errors import MealItemNotFoundError, MealNotFoundError
from app.logging import get_logger

logger = get_logger(__name__)


def delete_meal(session: Session, *, meal_id: int) -> dict[str, bool]:
    """Hard-delete a meal and its items (CASCADE). Returns ``{deleted: True}``."""

    meal = session.get(Meal, meal_id)
    if meal is None:
        raise MealNotFoundError(meal_id)

    session.delete(meal)
    session.flush()
    logger.info("meal_deleted", meal_id=meal_id)
    return {"deleted": True}


def delete_meal_item(session: Session, *, item_id: int) -> dict[str, bool]:
    """Hard-delete a single meal item. Returns ``{deleted: True}``."""

    item = session.get(MealItem, item_id)
    if item is None:
        raise MealItemNotFoundError(item_id)

    session.delete(item)
    session.flush()
    logger.info("meal_item_deleted", item_id=item_id)
    return {"deleted": True}
