"""Tests for MCP-01: update_meal and update_meal_item domain functions.

Covers partial-update semantics for both functions, the food_id swap
validation matrix, the CHECK-constraint rejection for food-linked macro
edits, and that meal totals/delta_vs_target recompute correctly on read
(no snapshotting) after a quantity change.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import MealItem, MealType, QuantityUnit
from app.domain.day_aggregation import get_day
from app.domain.errors import (
    FoodNotFoundError,
    MealItemFoodLinkedError,
    MealItemMacrosRequiredError,
    MealItemNotFoundError,
    MealNotFoundError,
)
from app.domain.meal_editing import update_meal, update_meal_item


class TestUpdateMeal:
    def test_partial_update_meal_type_only(self, db_session: Session, make_meal) -> None:
        meal = make_meal(meal_type=MealType.lunch, notes="original")

        result = update_meal(db_session, meal_id=meal.id, meal_type=MealType.dinner)

        assert result.meal_type == MealType.dinner
        assert result.notes == "original"  # unchanged

    def test_logged_at_change_recomputes_local_date(self, db_session: Session, make_meal) -> None:
        meal = make_meal(
            logged_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            local_tz="Europe/Dublin",
            local_date=date(2026, 7, 26),
        )

        # 23:00 UTC on 2026-07-26 = 00:00 Dublin on 2026-07-27
        new_logged_at = datetime(2026, 7, 26, 23, 0, tzinfo=UTC)
        result = update_meal(db_session, meal_id=meal.id, logged_at=new_logged_at)

        assert result.logged_at == new_logged_at
        assert result.local_date == date(2026, 7, 27)
        assert result.local_tz == "Europe/Dublin"  # untouched

    def test_logged_at_requires_timezone_aware(self, db_session: Session, make_meal) -> None:
        meal = make_meal()

        with pytest.raises(ValueError, match="timezone-aware"):
            update_meal(
                db_session,
                meal_id=meal.id,
                logged_at=datetime(2026, 7, 26, 12, 0),  # noqa: DTZ001
            )

    def test_notes_sentinel_omit_leaves_unchanged(self, db_session: Session, make_meal) -> None:
        meal = make_meal(notes="keep me")

        result = update_meal(db_session, meal_id=meal.id, meal_type=MealType.snack)

        assert result.notes == "keep me"

    def test_notes_explicit_none_clears(self, db_session: Session, make_meal) -> None:
        meal = make_meal(notes="clear me")

        result = update_meal(db_session, meal_id=meal.id, notes=None)

        assert result.notes is None

    def test_notes_can_be_set(self, db_session: Session, make_meal) -> None:
        meal = make_meal(notes=None)

        result = update_meal(db_session, meal_id=meal.id, notes="new note")

        assert result.notes == "new note"

    def test_does_not_touch_items(
        self, db_session: Session, make_meal, make_meal_item, make_food
    ) -> None:
        food = make_food(calories=Decimal("100"))
        meal = make_meal()
        make_meal_item(meal=meal, food=food, quantity=Decimal("50"))

        result = update_meal(db_session, meal_id=meal.id, notes="fixed typo")

        assert len(result.items) == 1
        assert result.items[0].quantity == Decimal("50")

    def test_not_found_raises(self, db_session: Session) -> None:
        with pytest.raises(MealNotFoundError) as exc_info:
            update_meal(db_session, meal_id=999999, notes="x")
        assert exc_info.value.error == "meal_not_found"


class TestUpdateMealItemQuantity:
    def test_quantity_update_on_food_linked_item(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food(calories=Decimal("200"))
        item = make_meal_item(food=food, quantity=Decimal("100"), quantity_unit=QuantityUnit.g)

        result = update_meal_item(db_session, item_id=item.id, quantity=Decimal("50"))

        assert result.quantity == Decimal("50")
        assert result.macros.calories == Decimal("100")  # 200 * 50/100

    def test_quantity_unit_update(self, db_session: Session, make_food, make_meal_item) -> None:
        food = make_food()
        item = make_meal_item(food=food, quantity=Decimal("100"), quantity_unit=QuantityUnit.g)

        result = update_meal_item(db_session, item_id=item.id, quantity_unit=QuantityUnit.g)

        assert result.quantity_unit == QuantityUnit.g

    def test_not_found_raises(self, db_session: Session) -> None:
        with pytest.raises(MealItemNotFoundError) as exc_info:
            update_meal_item(db_session, item_id=999999, quantity=Decimal("1"))
        assert exc_info.value.error == "meal_item_not_found"

    def test_meal_totals_recompute_on_read_after_quantity_change(
        self, db_session: Session, make_food, make_meal, make_meal_item, make_target
    ) -> None:
        """No write-time snapshot: get_day reflects the new quantity immediately."""

        make_target(effective_from=date(2026, 1, 1), base_calories=2000)
        food = make_food(calories=Decimal("200"), protein_g=Decimal("10"))
        meal = make_meal(
            logged_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 26),
        )
        item = make_meal_item(meal=meal, food=food, quantity=Decimal("100"))

        before = get_day(db_session, day=date(2026, 7, 26))
        assert before.day_totals.calories == Decimal("200")

        update_meal_item(db_session, item_id=item.id, quantity=Decimal("200"))
        db_session.expire_all()

        after = get_day(db_session, day=date(2026, 7, 26))
        assert after.day_totals.calories == Decimal("400")
        assert after.delta_vs_target is not None
        assert after.delta_vs_target.calories == Decimal("400") - Decimal("2000")


class TestUpdateMealItemFoodLinkedMacroRejection:
    def test_editing_macro_on_food_linked_item_raises(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food()
        item = make_meal_item(food=food)

        with pytest.raises(MealItemFoodLinkedError) as exc_info:
            update_meal_item(db_session, item_id=item.id, calories=Decimal("999"))

        assert exc_info.value.error == "meal_item_food_linked"

    def test_editing_optional_macro_on_food_linked_item_raises(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food()
        item = make_meal_item(food=food)

        with pytest.raises(MealItemFoodLinkedError):
            update_meal_item(db_session, item_id=item.id, fiber_g=Decimal("5"))

    def test_swapping_food_id_while_supplying_macros_raises(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food_a = make_food(name="Food A")
        food_b = make_food(name="Food B")
        item = make_meal_item(food=food_a)

        with pytest.raises(MealItemFoodLinkedError):
            update_meal_item(db_session, item_id=item.id, food_id=food_b.id, calories=Decimal("50"))


class TestUpdateMealItemAdhocPartialUpdate:
    def test_partial_update_required_macro(self, db_session: Session, make_meal_item) -> None:
        item = make_meal_item(
            food_id=None,
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
        )

        result = update_meal_item(db_session, item_id=item.id, calories=Decimal("175"))

        assert result.macros.calories == Decimal("175")
        assert result.macros.protein_g == Decimal("6")  # unchanged

    def test_optional_macro_sentinel_omit_leaves_unchanged(
        self, db_session: Session, make_meal_item
    ) -> None:
        item = make_meal_item(
            food_id=None,
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
            fiber_g=Decimal("3"),
        )

        result = update_meal_item(db_session, item_id=item.id, calories=Decimal("160"))

        assert result.macros.fiber_g == Decimal("3")

    def test_optional_macro_explicit_none_clears(self, db_session: Session, make_meal_item) -> None:
        item = make_meal_item(
            food_id=None,
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
            fiber_g=Decimal("3"),
        )

        result = update_meal_item(db_session, item_id=item.id, fiber_g=None)

        assert result.macros.fiber_g is None


class TestUpdateMealItemFoodIdSwap:
    def test_swap_between_two_foods(self, db_session: Session, make_food, make_meal_item) -> None:
        food_a = make_food(name="Food A", calories=Decimal("100"))
        food_b = make_food(name="Food B", calories=Decimal("300"))
        item = make_meal_item(food=food_a, quantity=Decimal("100"))

        result = update_meal_item(db_session, item_id=item.id, food_id=food_b.id)

        assert result.food_id == food_b.id
        assert result.macros.calories == Decimal("300")

    def test_swap_to_nonexistent_food_raises(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food()
        item = make_meal_item(food=food)

        with pytest.raises(FoodNotFoundError):
            update_meal_item(db_session, item_id=item.id, food_id=999999)

    def test_food_linked_to_adhoc_missing_macros_raises(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food()
        item = make_meal_item(food=food)

        with pytest.raises(MealItemMacrosRequiredError) as exc_info:
            update_meal_item(db_session, item_id=item.id, food_id=None)

        assert exc_info.value.error == "meal_item_macros_required"

    def test_food_linked_to_adhoc_partial_macros_raises(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food()
        item = make_meal_item(food=food)

        with pytest.raises(MealItemMacrosRequiredError):
            update_meal_item(
                db_session,
                item_id=item.id,
                food_id=None,
                calories=Decimal("150"),
                protein_g=Decimal("6"),
                # carbs_g, fat_g missing
            )

    def test_food_linked_to_adhoc_with_full_macros_succeeds(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food()
        item = make_meal_item(food=food)

        result = update_meal_item(
            db_session,
            item_id=item.id,
            food_id=None,
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
        )

        assert result.food_id is None
        assert result.macros.calories == Decimal("150")
        assert result.macros.protein_g == Decimal("6")
        assert result.macros.carbs_g == Decimal("18")
        assert result.macros.fat_g == Decimal("5")

        # Persisted row honors the adhoc_macros CHECK: macros stored, food_id NULL.
        db_session.commit()
        row = db_session.get(MealItem, item.id)
        assert row is not None
        assert row.food_id is None
        assert row.calories == Decimal("150")

    def test_food_linked_to_adhoc_clears_stale_optional_macros(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food()
        item = make_meal_item(food=food)

        update_meal_item(
            db_session,
            item_id=item.id,
            food_id=None,
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
            # fiber_g/sat_fat_g/sodium_mg omitted -> optional, stay None
        )

        db_session.commit()
        row = db_session.get(MealItem, item.id)
        assert row is not None
        assert row.fiber_g is None
        assert row.sat_fat_g is None
        assert row.sodium_mg is None

    def test_adhoc_to_food_linked_clears_stored_macros(
        self, db_session: Session, make_food, make_meal_item
    ) -> None:
        food = make_food(calories=Decimal("250"))
        item = make_meal_item(
            food_id=None,
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
            fiber_g=Decimal("2"),
        )

        result = update_meal_item(db_session, item_id=item.id, food_id=food.id)

        assert result.food_id == food.id
        assert result.macros.calories == Decimal("250")  # computed live from food

        db_session.commit()
        row = db_session.get(MealItem, item.id)
        assert row is not None
        assert row.calories is None
        assert row.protein_g is None
        assert row.carbs_g is None
        assert row.fat_g is None
        assert row.fiber_g is None

    def test_food_id_omitted_and_already_adhoc_is_ordinary_partial_update(
        self, db_session: Session, make_meal_item
    ) -> None:
        """food_id omitted (sentinel) while already ad-hoc must not require full macros."""

        item = make_meal_item(
            food_id=None,
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
        )

        result = update_meal_item(db_session, item_id=item.id, quantity=Decimal("200"))

        assert result.quantity == Decimal("200")
        assert result.macros.calories == Decimal("150")
