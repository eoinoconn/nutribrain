"""One-line factory helpers for the transactional test harness (T-012).

Each factory takes the active :class:`~sqlalchemy.orm.Session` plus keyword
overrides, persists a row with sensible defaults, flushes so the primary key is
populated, and returns the ORM object. Defaults keep the ad-hoc-macro invariant
(section 6): food-backed items carry no macros, ad-hoc items carry them.

These are plain functions; ``conftest`` wraps them as session-bound fixtures so
tests can write ``make_food(name="Rice")`` in a single line.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.db import (
    Food,
    Meal,
    MealItem,
    MealItemSource,
    MealType,
    QuantityUnit,
    ServingUnit,
    Target,
    Template,
    TemplateItem,
)

# A fixed instant so meals land on a deterministic local_date by default. Any
# test asserting time-of-day behaviour should pass its own logged_at.
_DEFAULT_LOGGED_AT = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def create_food(session: Session, **overrides: Any) -> Food:
    """Persist a food with complete, valid nutrition defaults."""

    values: dict[str, Any] = {
        "name": "Test Food",
        "serving_size": Decimal("100"),
        "serving_unit": ServingUnit.g,
        "calories": Decimal("200"),
        "protein_g": Decimal("10"),
        "carbs_g": Decimal("20"),
        "fat_g": Decimal("8"),
    }
    values.update(overrides)
    food = Food(**values)
    session.add(food)
    session.flush()
    return food


def create_meal(session: Session, **overrides: Any) -> Meal:
    """Persist a meal, deriving ``local_date`` from ``logged_at`` when absent."""

    logged_at: datetime = overrides.pop("logged_at", _DEFAULT_LOGGED_AT)
    local_tz: str = overrides.pop("local_tz", "Europe/Dublin")
    values: dict[str, Any] = {
        "logged_at": logged_at,
        "local_tz": local_tz,
        "local_date": logged_at.date(),
        "meal_type": MealType.lunch,
    }
    values.update(overrides)
    meal = Meal(**values)
    session.add(meal)
    session.flush()
    return meal


def create_meal_item(session: Session, **overrides: Any) -> MealItem:
    """Persist a meal item.

    Passing ``food`` or ``food_id`` produces a food-backed item (macros stay
    ``None``, computed at read time); otherwise an ad-hoc item is created with
    stored macros, honouring the section-6 invariant.
    """

    food = overrides.pop("food", None)
    if food is not None and "food_id" not in overrides:
        overrides["food_id"] = food.id

    if "meal_id" not in overrides:
        overrides["meal_id"] = create_meal(session).id

    is_food_backed = overrides.get("food_id") is not None
    values: dict[str, Any] = {
        "name": "Test Item",
        "quantity": Decimal("100"),
        "quantity_unit": QuantityUnit.g,
        "source": MealItemSource.label if is_food_backed else MealItemSource.estimate,
    }
    if not is_food_backed:
        values.update(
            {
                "calories": Decimal("150"),
                "protein_g": Decimal("6"),
                "carbs_g": Decimal("18"),
                "fat_g": Decimal("5"),
            }
        )
    values.update(overrides)
    item = MealItem(**values)
    session.add(item)
    session.flush()
    return item


def create_template(session: Session, **overrides: Any) -> Template:
    """Persist a template."""

    values: dict[str, Any] = {"name": "Test Template"}
    values.update(overrides)
    template = Template(**values)
    session.add(template)
    session.flush()
    return template


def create_template_item(session: Session, **overrides: Any) -> TemplateItem:
    """Persist a template item, mirroring :func:`create_meal_item` semantics."""

    food = overrides.pop("food", None)
    if food is not None and "food_id" not in overrides:
        overrides["food_id"] = food.id

    if "template_id" not in overrides:
        overrides["template_id"] = create_template(session).id

    is_food_backed = overrides.get("food_id") is not None
    values: dict[str, Any] = {
        "name": "Test Item",
        "quantity": Decimal("100"),
        "quantity_unit": QuantityUnit.g,
    }
    if not is_food_backed:
        values.update(
            {
                "calories": Decimal("150"),
                "protein_g": Decimal("6"),
                "carbs_g": Decimal("18"),
                "fat_g": Decimal("5"),
            }
        )
    values.update(overrides)
    item = TemplateItem(**values)
    session.add(item)
    session.flush()
    return item


def create_target(session: Session, **overrides: Any) -> Target:
    """Persist a versioned target row."""

    values: dict[str, Any] = {
        "effective_from": date(2026, 1, 1),
        "base_calories": 2200,
        "protein_g": 150,
        "carbs_g": 220,
        "fat_g": 70,
    }
    values.update(overrides)
    target = Target(**values)
    session.add(target)
    session.flush()
    return target
