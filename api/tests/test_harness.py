"""Tests for the transactional test harness itself (T-012).

The load-bearing assertion is isolation: two tests that write *conflicting* data
must both pass regardless of execution order, proving the per-test transaction
is rolled back on teardown.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Food, MealItem, Target, TemplateItem
from tests.conftest import FROZEN_INSTANT, FrozenClock


def _food_count(session: Session) -> int:
    return session.execute(select(func.count()).select_from(Food)).scalar_one()


def test_isolation_first_writer(db_session: Session) -> None:
    # Explicit primary key so a leaked row from another test would collide.
    db_session.add(
        Food(
            id=1,
            name="Conflicting Food",
            serving_size=Decimal("100"),
            serving_unit="g",
            calories=Decimal("200"),
            protein_g=Decimal("10"),
            carbs_g=Decimal("20"),
            fat_g=Decimal("8"),
        )
    )
    db_session.flush()
    assert _food_count(db_session) == 1


def test_isolation_second_writer(db_session: Session) -> None:
    # Same id and name as the other isolation test. Passes only because the
    # first test's transaction was rolled back before this one began.
    db_session.add(
        Food(
            id=1,
            name="Conflicting Food",
            serving_size=Decimal("100"),
            serving_unit="g",
            calories=Decimal("999"),
            protein_g=Decimal("1"),
            carbs_g=Decimal("1"),
            fat_g=Decimal("1"),
        )
    )
    db_session.flush()
    assert _food_count(db_session) == 1


def test_commit_inside_test_is_still_rolled_back(db_session: Session) -> None:
    # create_savepoint mode means an in-test commit only releases a savepoint;
    # teardown's outer rollback still discards the row. If it did not, the two
    # isolation tests above would flake depending on order.
    db_session.add(
        Food(
            name="Committed Food",
            serving_size=Decimal("100"),
            serving_unit="g",
            calories=Decimal("100"),
            protein_g=Decimal("1"),
            carbs_g=Decimal("1"),
            fat_g=Decimal("1"),
        )
    )
    db_session.commit()
    assert _food_count(db_session) == 1


def test_make_food_one_line(make_food: Callable[..., Food]) -> None:
    food = make_food(name="Rice")
    assert food.id is not None
    assert food.name == "Rice"


def test_make_food_backed_meal_item(
    make_food: Callable[..., Food], make_meal_item: Callable[..., MealItem]
) -> None:
    food = make_food(name="Oats")
    item = make_meal_item(food=food)
    # Food-backed items store no macros; they are computed at read time.
    assert item.food_id == food.id
    assert item.calories is None


def test_make_adhoc_meal_item_stores_macros(make_meal_item: Callable[..., MealItem]) -> None:
    item = make_meal_item(name="Mystery snack")
    assert item.food_id is None
    assert item.calories is not None


def test_food_backed_meal_item_persists(
    db_session: Session,
    make_meal_item: Callable[..., MealItem],
    make_food: Callable[..., Food],
) -> None:
    food = make_food()
    make_meal_item(food=food)
    stored = db_session.execute(select(MealItem)).scalar_one()
    assert stored.food_id == food.id


def test_template_item_factory(
    db_session: Session, make_template_item: Callable[..., TemplateItem]
) -> None:
    make_template_item()
    stored = db_session.execute(select(TemplateItem)).scalar_one()
    assert stored.calories is not None


def test_make_target_one_line(make_target: Callable[..., Target]) -> None:
    target = make_target(base_calories=2500)
    assert target.id is not None
    assert target.base_calories == 2500


def test_frozen_clock_is_deterministic(frozen_clock: FrozenClock) -> None:
    assert frozen_clock.now() == FROZEN_INSTANT
    # Repeated reads never move.
    assert frozen_clock.now() == frozen_clock.now()


def test_frozen_clock_advances(frozen_clock: FrozenClock) -> None:
    frozen_clock.advance(timedelta(hours=3))
    assert frozen_clock.now() == FROZEN_INSTANT + timedelta(hours=3)


def test_frozen_clock_rejects_naive_instant() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 7, 26, 12, 0))  # noqa: DTZ001


def test_frozen_clock_converts_timezone(frozen_clock: FrozenClock) -> None:
    # 12:00 UTC is still the same instant expressed in another zone.
    utc_value = frozen_clock.now(UTC)
    assert utc_value == FROZEN_INSTANT
