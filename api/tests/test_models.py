"""Schema-level tests for the ad-hoc-macro CHECK constraint (T-010).

These run against in-memory SQLite so they do not depend on the Postgres test
harness (T-012). They assert the invariant from §6: a meal_item / template_item
carries macros if and only if food_id IS NULL.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.db import Base, MealItem, MealItemSource, QuantityUnit, TemplateItem


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite://")

    # SQLite ignores CHECK constraints only when compiled without support; the
    # bundled build enforces them. Foreign keys are off by default, which is
    # fine here — we are exercising the macro CHECK, not referential integrity.
    @event.listens_for(eng, "connect")
    def _enforce_checks(dbapi_conn: sqlite3.Connection, _record: object) -> None:
        dbapi_conn.execute("PRAGMA ignore_check_constraints = OFF")

    Base.metadata.create_all(eng)
    return eng


def test_meal_item_food_ref_rejects_stored_macros(engine: Engine) -> None:
    # food_id set + macros present is a mixed-mode row and must be rejected.
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            insert(MealItem).values(
                meal_id=1,
                food_id=1,
                name="rice",
                quantity=100,
                quantity_unit=QuantityUnit.g,
                calories=130,
                source=MealItemSource.label,
            )
        )


def test_meal_item_adhoc_requires_macros(engine: Engine) -> None:
    # food_id NULL with no macros is the other mixed-mode failure.
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            insert(MealItem).values(
                meal_id=1,
                food_id=None,
                name="mystery snack",
                quantity=1,
                quantity_unit=QuantityUnit.serving,
                source=MealItemSource.estimate,
            )
        )


def test_meal_item_food_ref_without_macros_is_valid(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(MealItem).values(
                meal_id=1,
                food_id=1,
                name="rice",
                quantity=100,
                quantity_unit=QuantityUnit.g,
                source=MealItemSource.label,
            )
        )


def test_meal_item_adhoc_with_macros_is_valid(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(MealItem).values(
                meal_id=1,
                food_id=None,
                name="mystery snack",
                quantity=1,
                quantity_unit=QuantityUnit.serving,
                calories=250,
                protein_g=8,
                carbs_g=30,
                fat_g=10,
                source=MealItemSource.estimate,
            )
        )


def test_template_item_food_ref_rejects_stored_macros(engine: Engine) -> None:
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            insert(TemplateItem).values(
                template_id=1,
                food_id=1,
                name="rice",
                quantity=100,
                quantity_unit=QuantityUnit.g,
                calories=130,
            )
        )
