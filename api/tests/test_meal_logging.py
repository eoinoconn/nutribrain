"""Tests for T-023: log_meal domain function."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import Food, MealItem, MealItemSource, MealType, QuantityUnit, ServingUnit, Target
from app.domain import (
    MealItemSpec,
    log_meal,
)
from app.domain.errors import FoodAmbiguousError, FoodNotFoundError


@pytest.fixture
def frozen_logged_at() -> datetime:
    """A fixed timestamp for deterministic testing: 2026-07-26 12:00 UTC."""
    return datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def dublin_tz() -> str:
    """Europe/Dublin timezone."""
    return "Europe/Dublin"


def test_log_meal_mixed_resolution(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test a mixed meal: food-backed, ad-hoc, and favorite-resolved items.

    This is the spec's definitive test case (§3): one food-backed item, one
    ad-hoc item with stored macros, one item resolved via favorite matching.
    """

    # Create three foods
    food_backed = Food(
        id=1,
        name="Oats",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("389"),
        protein_g=Decimal("16.7"),
        carbs_g=Decimal("66.3"),
        fat_g=Decimal("6.9"),
    )
    db_session.add(food_backed)

    favorite_food = Food(
        id=2,
        name="Banana",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("89"),
        protein_g=Decimal("1.1"),
        carbs_g=Decimal("23"),
        fat_g=Decimal("0.3"),
        is_favorite=True,
    )
    db_session.add(favorite_food)

    db_session.flush()

    # Items spec: food-backed, ad-hoc, and favorite by name
    items = [
        MealItemSpec(
            name="Oats",
            quantity=Decimal("50"),
            quantity_unit=QuantityUnit.g,
            food_id=food_backed.id,  # Explicit food_id
        ),
        MealItemSpec(
            name="Yogurt",
            quantity=Decimal("150"),
            quantity_unit=QuantityUnit.g,
            calories=Decimal("75"),
            protein_g=Decimal("15"),
            carbs_g=Decimal("7"),
            fat_g=Decimal("0"),
        ),
        MealItemSpec(
            name="Banana",  # Resolves to favorite
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
        ),
    ]

    # Log the meal
    response = log_meal(
        db_session,
        items=items,
        logged_at=frozen_logged_at,
        local_tz=dublin_tz,
        meal_type="breakfast",
    )

    # Verify meal was created
    assert response.id is not None
    assert response.meal_type == MealType.breakfast
    assert response.local_date == date(2026, 7, 26)  # 12:00 UTC = 13:00 Dublin

    # Verify three items were logged
    assert len(response.items) == 3

    # Item 0: food-backed (50g oats)
    item0 = response.items[0]
    assert item0.food_id == food_backed.id
    assert item0.name == "Oats"
    assert item0.source == MealItemSource.label
    assert item0.macros.calories == Decimal("194.5")  # 389 * 50/100
    assert item0.macros.protein_g == Decimal("8.35")

    # Item 1: ad-hoc (yogurt with supplied macros)
    item1 = response.items[1]
    assert item1.food_id is None
    assert item1.name == "Yogurt"
    assert item1.source == MealItemSource.estimate
    assert item1.macros.calories == Decimal("75")
    assert item1.macros.protein_g == Decimal("15")

    # Item 2: favorite-resolved (100g banana)
    item2 = response.items[2]
    assert item2.food_id == favorite_food.id
    assert item2.name == "Banana"
    assert item2.source == MealItemSource.label
    assert item2.macros.calories == Decimal("89")

    # Verify totals
    assert response.totals.calories == Decimal("358.5")  # 194.5 + 75 + 89
    assert response.totals.protein_g == Decimal("24.45")  # 8.35 + 15 + 1.1


def test_log_meal_with_target_delta(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test that delta vs. target is computed correctly."""

    # Create a food
    food = Food(
        name="Rice",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("130"),
        protein_g=Decimal("2.7"),
        carbs_g=Decimal("28"),
        fat_g=Decimal("0.3"),
    )
    db_session.add(food)

    # Create a target for this date
    target = Target(
        effective_from=date(2026, 7, 26),
        base_calories=2000,
        protein_g=150,
        carbs_g=200,
        fat_g=70,
    )
    db_session.add(target)
    db_session.flush()

    items = [
        MealItemSpec(
            name="Rice",
            quantity=Decimal("200"),
            quantity_unit=QuantityUnit.g,
            food_id=food.id,
        ),
    ]

    response = log_meal(
        db_session,
        items=items,
        logged_at=frozen_logged_at,
        local_tz=dublin_tz,
    )

    # Meal totals: 260 cal, 5.4g protein, 56g carbs, 0.6g fat
    assert response.totals.calories == Decimal("260")

    # Delta = meal - target
    # Negative delta means under target
    assert response.delta_vs_target is not None
    assert response.delta_vs_target.calories == Decimal("-1740")  # 260 - 2000
    assert response.delta_vs_target.protein_g == Decimal("-144.6")  # 5.4 - 150


def test_log_meal_without_target_returns_none_delta(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test that delta is None when no target is set."""

    food = Food(
        name="Eggs",
        serving_size=Decimal("50"),
        serving_unit=ServingUnit.g,
        calories=Decimal("155"),
        protein_g=Decimal("13"),
        carbs_g=Decimal("1.1"),
        fat_g=Decimal("11"),
    )
    db_session.add(food)
    db_session.flush()

    items = [
        MealItemSpec(
            name="Eggs",
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
            food_id=food.id,
        ),
    ]

    response = log_meal(
        db_session,
        items=items,
        logged_at=frozen_logged_at,
        local_tz=dublin_tz,
    )

    assert response.delta_vs_target is None


def test_log_meal_ambiguous_resolution_raises(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test that ambiguous resolution without macros raises FoodAmbiguousError."""

    # Create two foods that will be fuzzy-matched
    food1 = Food(
        name="Apple Juice",
        serving_size=Decimal("250"),
        serving_unit=ServingUnit.ml,
        calories=Decimal("117"),
        protein_g=Decimal("0.5"),
        carbs_g=Decimal("29"),
        fat_g=Decimal("0.3"),
    )
    food2 = Food(
        name="Apple Cider",
        serving_size=Decimal("250"),
        serving_unit=ServingUnit.ml,
        calories=Decimal("117"),
        protein_g=Decimal("0.1"),
        carbs_g=Decimal("28"),
        fat_g=Decimal("0.3"),
    )
    db_session.add(food1)
    db_session.add(food2)
    db_session.flush()

    items = [
        MealItemSpec(
            name="Apple",  # Fuzzy match, matches both
            quantity=Decimal("250"),
            quantity_unit=QuantityUnit.ml,
            # No food_id, no macros → must resolve via fuzzy match
        ),
    ]

    with pytest.raises(FoodAmbiguousError) as exc_info:
        log_meal(
            db_session,
            items=items,
            logged_at=frozen_logged_at,
            local_tz=dublin_tz,
        )

    # Check the error includes candidates
    assert "Apple" in str(exc_info.value)
    assert exc_info.value.candidates is not None
    assert len(exc_info.value.candidates) > 0


def test_log_meal_not_found_without_macros_raises(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test that unresolvable items without macros raise FoodNotFoundError."""

    items = [
        MealItemSpec(
            name="Unknown Mystery Food",
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
            # No food_id, no macros
        ),
    ]

    with pytest.raises(FoodNotFoundError):
        log_meal(
            db_session,
            items=items,
            logged_at=frozen_logged_at,
            local_tz=dublin_tz,
        )


def test_log_meal_unresolved_food_with_macros_logs_adhoc(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test that unresolved items with macros are logged as ad-hoc."""

    items = [
        MealItemSpec(
            name="Unknown food",
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
            calories=Decimal("150"),
            protein_g=Decimal("5"),
            carbs_g=Decimal("25"),
            fat_g=Decimal("4"),
        ),
    ]

    response = log_meal(
        db_session,
        items=items,
        logged_at=frozen_logged_at,
        local_tz=dublin_tz,
    )

    assert len(response.items) == 1
    item = response.items[0]
    assert item.food_id is None
    assert item.name == "Unknown food"
    assert item.source == MealItemSource.estimate
    assert item.macros.calories == Decimal("150")


def test_log_meal_local_date_derived_from_timezone(
    db_session: Session,
) -> None:
    """Test that local_date is correctly derived from logged_at and local_tz.

    A 23:00 UTC meal in Dublin is 00:00 the next day locally.
    """

    food = Food(
        name="Test",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("100"),
        protein_g=Decimal("1"),
        carbs_g=Decimal("20"),
        fat_g=Decimal("1"),
    )
    db_session.add(food)
    db_session.flush()

    # 23:00 UTC on 2026-07-26
    logged_at = datetime(2026, 7, 26, 23, 0, tzinfo=UTC)
    dublin_tz = "Europe/Dublin"

    items = [
        MealItemSpec(
            name="Test",
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
            food_id=food.id,
        ),
    ]

    response = log_meal(
        db_session,
        items=items,
        logged_at=logged_at,
        local_tz=dublin_tz,
    )

    # 23:00 UTC = 00:00 Dublin (next day)
    assert response.local_date == date(2026, 7, 27)


def test_log_meal_meal_type_inference(
    db_session: Session,
) -> None:
    """Test that meal_type is inferred correctly from time of day.

    Breakfast: 04:00-10:59
    Lunch: 11:00-15:59
    Dinner: 16:00-21:59
    Snack: 22:00-03:59
    """

    food = Food(
        name="Test",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("100"),
        protein_g=Decimal("1"),
        carbs_g=Decimal("20"),
        fat_g=Decimal("1"),
    )
    db_session.add(food)
    db_session.flush()

    items = [
        MealItemSpec(
            name="Test",
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
            food_id=food.id,
        ),
    ]

    # 08:00 UTC = 09:00 Dublin (breakfast window)
    response = log_meal(
        db_session,
        items=items,
        logged_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        local_tz="Europe/Dublin",
    )
    assert response.meal_type == MealType.breakfast

    # Clear the item for next test
    db_session.query(MealItem).delete()
    db_session.flush()

    # 12:00 UTC = 13:00 Dublin (lunch window)
    response = log_meal(
        db_session,
        items=items,
        logged_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
        local_tz="Europe/Dublin",
    )
    assert response.meal_type == MealType.lunch


def test_log_meal_explicit_meal_type_overrides_inference(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test that explicitly provided meal_type overrides inference."""

    food = Food(
        name="Test",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("100"),
        protein_g=Decimal("1"),
        carbs_g=Decimal("20"),
        fat_g=Decimal("1"),
    )
    db_session.add(food)
    db_session.flush()

    items = [
        MealItemSpec(
            name="Test",
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
            food_id=food.id,
        ),
    ]

    # 12:00 UTC would normally be lunch, but we override to snack
    response = log_meal(
        db_session,
        items=items,
        logged_at=frozen_logged_at,  # 12:00 UTC
        local_tz=dublin_tz,
        meal_type="snack",
    )
    assert response.meal_type == MealType.snack


def test_log_meal_persists_to_database(
    db_session: Session,
    frozen_logged_at: datetime,
    dublin_tz: str,
) -> None:
    """Test that the created meal and items are persisted."""

    from app.db import Meal as MealModel

    food = Food(
        name="Test",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("100"),
        protein_g=Decimal("5"),
        carbs_g=Decimal("20"),
        fat_g=Decimal("2"),
    )
    db_session.add(food)
    db_session.flush()

    items = [
        MealItemSpec(
            name="Test",
            quantity=Decimal("100"),
            quantity_unit=QuantityUnit.g,
            food_id=food.id,
        ),
    ]

    response = log_meal(
        db_session,
        items=items,
        logged_at=frozen_logged_at,
        local_tz=dublin_tz,
    )

    # Flush and refresh to ensure it's in the DB
    db_session.commit()

    # Query it back out
    meal = db_session.get(MealModel, response.id)
    assert meal is not None
    assert meal.logged_at == frozen_logged_at
    assert len(meal.items) == 1
