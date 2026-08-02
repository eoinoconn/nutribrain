"""Tests for foods domain operations (T-024).

Validates:
- add_food with fuzzy-duplicate detection and force override
- update_food partial update, rejecting serving_unit changes
- update_food returns count of affected past meals
- Changing calories on a food changes the totals of an already-logged meal
- set_favorite_food and soft delete
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import ServingUnit
from app.domain import (
    FoodDuplicateError,
    FoodMergeSameFoodError,
    FoodNotFoundError,
    ServingUnitImmutableError,
    add_food,
    compute_item_macros,
    delete_food,
    merge_food,
    search_foods,
    set_favorite_food,
    update_food,
)


class TestAddFood:
    def test_add_food_creates_food(self, db_session: Session) -> None:
        result = add_food(
            db_session,
            name="Oats",
            serving_size=Decimal("40"),
            serving_unit=ServingUnit.g,
            calories=Decimal("150"),
            protein_g=Decimal("5"),
            carbs_g=Decimal("27"),
            fat_g=Decimal("3"),
        )

        assert result.food.id is not None
        assert result.food.name == "Oats"
        assert result.food.calories == Decimal("150")

    def test_add_food_raises_duplicate_on_similar_name(
        self, db_session: Session, make_food
    ) -> None:
        make_food(name="Overnight Oats")

        with pytest.raises(FoodDuplicateError) as exc_info:
            add_food(
                db_session,
                name="Overnight Oats",
                serving_size=Decimal("40"),
                serving_unit=ServingUnit.g,
                calories=Decimal("150"),
                protein_g=Decimal("5"),
                carbs_g=Decimal("27"),
                fat_g=Decimal("3"),
            )

        assert exc_info.value.error == "food_duplicate"
        assert exc_info.value.candidates is not None
        assert len(exc_info.value.candidates) > 0

    def test_add_food_force_bypasses_duplicate_check(self, db_session: Session, make_food) -> None:
        make_food(name="Overnight Oats")

        result = add_food(
            db_session,
            name="Overnight Oats",
            serving_size=Decimal("80"),
            serving_unit=ServingUnit.g,
            calories=Decimal("300"),
            protein_g=Decimal("10"),
            carbs_g=Decimal("54"),
            fat_g=Decimal("6"),
            force=True,
        )

        assert result.food.id is not None
        assert result.food.name == "Overnight Oats"

    def test_add_food_strips_name_whitespace(self, db_session: Session) -> None:
        result = add_food(
            db_session,
            name="  Rice  ",
            serving_size=Decimal("100"),
            serving_unit=ServingUnit.g,
            calories=Decimal("130"),
            protein_g=Decimal("3"),
            carbs_g=Decimal("28"),
            fat_g=Decimal("0.3"),
        )

        assert result.food.name == "Rice"


class TestUpdateFood:
    def test_update_food_partial_update(self, db_session: Session, make_food) -> None:
        food = make_food(name="Chicken Breast", calories=Decimal("165"))

        result = update_food(db_session, food_id=food.id, calories=Decimal("170"))

        assert result.food.calories == Decimal("170")
        assert result.food.name == "Chicken Breast"  # unchanged

    def test_update_food_rejects_serving_unit_change(self, db_session: Session, make_food) -> None:
        food = make_food(serving_unit=ServingUnit.g)

        with pytest.raises(ServingUnitImmutableError) as exc_info:
            update_food(db_session, food_id=food.id, serving_unit=ServingUnit.ml)

        assert exc_info.value.error == "serving_unit_immutable"

    def test_update_food_returns_affected_meals_count(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food(name="Rice", calories=Decimal("130"))
        meal1 = make_meal()
        meal2 = make_meal()
        make_meal_item(food=food, meal_id=meal1.id)
        make_meal_item(food=food, meal_id=meal2.id)

        result = update_food(db_session, food_id=food.id, calories=Decimal("135"))

        assert result.affected_meals_count == 2

    def test_update_food_not_found_raises(self, db_session: Session) -> None:
        with pytest.raises(FoodNotFoundError):
            update_food(db_session, food_id=999999, calories=Decimal("100"))

    def test_update_food_nullable_fields_can_be_set_to_none(
        self, db_session: Session, make_food
    ) -> None:
        food = make_food(fiber_g=Decimal("3"))

        result = update_food(db_session, food_id=food.id, fiber_g=None)

        assert result.food.fiber_g is None


class TestCaloriesPropagation:
    """Asserts that changing calories on a food changes the totals of a historical meal."""

    def test_changing_calories_propagates_to_historical_meal(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        """Core requirement: editing food.calories recomputes past meals at read time."""

        food = make_food(
            name="Granola",
            serving_size=Decimal("100"),
            serving_unit=ServingUnit.g,
            calories=Decimal("400"),
            protein_g=Decimal("10"),
            carbs_g=Decimal("60"),
            fat_g=Decimal("15"),
        )
        meal = make_meal()
        item = make_meal_item(food=food, meal_id=meal.id, quantity=Decimal("100"))

        # Before update: 400 calories for 100g of a 100g serving
        macros_before = compute_item_macros(item, food)
        assert macros_before.calories == Decimal("400")

        # Update food calories
        update_food(db_session, food_id=food.id, calories=Decimal("380"))

        # After update: the same meal_item now reads 380 calories
        db_session.refresh(food)
        macros_after = compute_item_macros(item, food)
        assert macros_after.calories == Decimal("380")


class TestSetFavoriteFood:
    def test_set_favorite_food(self, db_session: Session, make_food) -> None:
        food = make_food(is_favorite=False)

        result = set_favorite_food(db_session, food_id=food.id, is_favorite=True)

        assert result.is_favorite is True

    def test_unset_favorite_food(self, db_session: Session, make_food) -> None:
        food = make_food(is_favorite=True)

        result = set_favorite_food(db_session, food_id=food.id, is_favorite=False)

        assert result.is_favorite is False

    def test_set_favorite_food_not_found(self, db_session: Session) -> None:
        with pytest.raises(FoodNotFoundError):
            set_favorite_food(db_session, food_id=999999, is_favorite=True)


class TestDeleteFood:
    def test_soft_delete_food(self, db_session: Session, make_food) -> None:
        food = make_food()

        result = delete_food(db_session, food_id=food.id)

        assert result.deleted_at is not None

    def test_delete_food_not_found(self, db_session: Session) -> None:
        with pytest.raises(FoodNotFoundError):
            delete_food(db_session, food_id=999999)

    def test_delete_food_already_deleted(self, db_session: Session, make_food) -> None:
        food = make_food()
        delete_food(db_session, food_id=food.id)

        with pytest.raises(FoodNotFoundError):
            delete_food(db_session, food_id=food.id)


class TestSearchFoodsNormalizedMatch:
    """MCP-06: normalized substring pre-filter for queries with extra words/spacing."""

    def test_search_foods_matches_query_with_trailing_extra_word(
        self, db_session: Session, make_food
    ) -> None:
        make_food(name="GetPRO")

        results = search_foods(db_session, query="getpro yogurt")

        assert any(r.food.name == "GetPRO" for r in results)

    def test_search_foods_matches_query_with_internal_space_and_extra_word(
        self, db_session: Session, make_food
    ) -> None:
        make_food(name="GetPRO")

        results = search_foods(db_session, query="get pro yogurt")

        assert any(r.food.name == "GetPRO" for r in results)


class TestMergeFood:
    def test_merge_food_reassigns_meal_items_and_leaves_others_untouched(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        from_food = make_food(name="Duplicate Yogurt")
        into_food = make_food(name="GetPRO")
        other_food = make_food(name="Unrelated Food")

        meal = make_meal()
        item = make_meal_item(food=from_food, meal_id=meal.id)
        other_item = make_meal_item(food=other_food, meal_id=meal.id)

        result = merge_food(db_session, from_id=from_food.id, into_id=into_food.id)

        db_session.refresh(item)
        db_session.refresh(other_item)
        assert item.food_id == into_food.id
        assert other_item.food_id == other_food.id
        assert result.reassigned_count == 1

    def test_merge_food_soft_deletes_from_food_and_excludes_it_from_search(
        self, db_session: Session, make_food
    ) -> None:
        from_food = make_food(name="Duplicate Yogurt")
        into_food = make_food(name="GetPRO")

        result = merge_food(db_session, from_id=from_food.id, into_id=into_food.id)

        assert result.from_food.deleted_at is not None
        results = search_foods(db_session, query="Duplicate Yogurt")
        assert all(r.food.id != from_food.id for r in results)

    def test_merge_food_into_nonexistent_raises_not_found(
        self, db_session: Session, make_food
    ) -> None:
        from_food = make_food(name="Duplicate Yogurt")

        with pytest.raises(FoodNotFoundError):
            merge_food(db_session, from_id=from_food.id, into_id=999999)

    def test_merge_food_from_already_deleted_raises_not_found(
        self, db_session: Session, make_food
    ) -> None:
        from_food = make_food(name="Duplicate Yogurt")
        into_food = make_food(name="GetPRO")
        delete_food(db_session, food_id=from_food.id)

        with pytest.raises(FoodNotFoundError):
            merge_food(db_session, from_id=from_food.id, into_id=into_food.id)

    def test_merge_food_into_already_deleted_raises_not_found(
        self, db_session: Session, make_food
    ) -> None:
        from_food = make_food(name="Duplicate Yogurt")
        into_food = make_food(name="GetPRO")
        delete_food(db_session, food_id=into_food.id)

        with pytest.raises(FoodNotFoundError):
            merge_food(db_session, from_id=from_food.id, into_id=into_food.id)

    def test_merge_food_self_merge_raises_domain_error(
        self, db_session: Session, make_food
    ) -> None:
        food = make_food(name="GetPRO")

        with pytest.raises(FoodMergeSameFoodError) as exc_info:
            merge_food(db_session, from_id=food.id, into_id=food.id)

        assert exc_info.value.error == "food_merge_same_food"

    def test_merge_food_reassigned_items_compute_against_into_foods_current_macros(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        """No macro snapshot is taken on merge: reassigned items compute live."""

        from_food = make_food(
            name="Duplicate Yogurt",
            serving_size=Decimal("100"),
            serving_unit=ServingUnit.g,
            calories=Decimal("100"),
            protein_g=Decimal("10"),
            carbs_g=Decimal("10"),
            fat_g=Decimal("1"),
        )
        into_food = make_food(
            name="GetPRO",
            serving_size=Decimal("100"),
            serving_unit=ServingUnit.g,
            calories=Decimal("500"),
            protein_g=Decimal("50"),
            carbs_g=Decimal("40"),
            fat_g=Decimal("10"),
        )
        meal = make_meal()
        item = make_meal_item(food=from_food, meal_id=meal.id, quantity=Decimal("100"))

        merge_food(db_session, from_id=from_food.id, into_id=into_food.id)

        db_session.refresh(item)
        db_session.refresh(into_food)
        macros = compute_item_macros(item, into_food)
        assert macros.calories == Decimal("500")
