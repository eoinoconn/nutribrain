"""Tests for MCP-02: copy_meal.

Covers the materialization contract (food-linked items stay live-computed,
ad-hoc items copy their macro snapshot), quantity_scale, to_day/at resolution,
meal_type carry-forward, notes defaulting, and the not-found error.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import MealType
from app.domain.errors import MealNotFoundError
from app.domain.meal_copying import copy_meal


class TestCopyMealMaterialization:
    def test_food_linked_item_stays_live_computed(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food(calories=Decimal("200"))
        meal = make_meal()
        make_meal_item(meal=meal, food=food, quantity=Decimal("100"))

        result = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin")

        assert len(result.items) == 1
        assert result.items[0].food_id == food.id
        assert result.totals.calories == Decimal("200")

        # Changing the food's calories after the copy changes the copy's totals
        # too, proving no macro snapshot was taken at copy time.
        food.calories = Decimal("400")
        db_session.flush()

        recomputed = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin")
        assert recomputed.totals.calories == Decimal("400")

    def test_adhoc_item_copies_stored_macro_snapshot(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        meal = make_meal()
        make_meal_item(
            meal=meal,
            food_id=None,
            quantity=Decimal("1"),
            calories=Decimal("150"),
            protein_g=Decimal("6"),
            carbs_g=Decimal("18"),
            fat_g=Decimal("5"),
            fiber_g=Decimal("3"),
        )

        result = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin")

        assert len(result.items) == 1
        copied_item = result.items[0]
        assert copied_item.food_id is None
        assert copied_item.macros.calories == Decimal("150")
        assert copied_item.macros.protein_g == Decimal("6")
        assert copied_item.macros.carbs_g == Decimal("18")
        assert copied_item.macros.fat_g == Decimal("5")
        assert copied_item.macros.fiber_g == Decimal("3")

    def test_multiple_items_all_copied(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food(calories=Decimal("100"))
        meal = make_meal()
        make_meal_item(meal=meal, food=food, quantity=Decimal("50"))
        make_meal_item(
            meal=meal,
            food_id=None,
            quantity=Decimal("1"),
            calories=Decimal("80"),
            protein_g=Decimal("2"),
            carbs_g=Decimal("10"),
            fat_g=Decimal("1"),
        )

        result = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin")

        assert len(result.items) == 2
        # Original meal's items are untouched.
        assert len(meal.items) == 2


class TestCopyMealQuantityScale:
    def test_quantity_scale_multiplies_every_item(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food(calories=Decimal("100"))
        meal = make_meal()
        make_meal_item(meal=meal, food=food, quantity=Decimal("50"))
        make_meal_item(
            meal=meal,
            food_id=None,
            quantity=Decimal("2"),
            calories=Decimal("80"),
            protein_g=Decimal("2"),
            carbs_g=Decimal("10"),
            fat_g=Decimal("1"),
        )

        result = copy_meal(
            db_session, meal_id=meal.id, local_tz="Europe/Dublin", quantity_scale=Decimal("2")
        )

        by_food_linked = {item.food_id is not None: item for item in result.items}
        assert by_food_linked[True].quantity == Decimal("100")
        assert by_food_linked[False].quantity == Decimal("4")
        assert by_food_linked[False].macros.calories == Decimal("160")  # 80 * 2

    def test_quantity_scale_defaults_to_one_when_omitted(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal()
        make_meal_item(meal=meal, food=food, quantity=Decimal("75"))

        result = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin")

        assert result.items[0].quantity == Decimal("75")


class TestCopyMealDayAndTime:
    def test_to_day_and_at_resolve_logged_at(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal(
            logged_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
            local_tz="Europe/Dublin",
            local_date=date(2026, 7, 26),
        )
        make_meal_item(meal=meal, food=food)

        result = copy_meal(
            db_session,
            meal_id=meal.id,
            local_tz="Europe/Dublin",
            to_day="2026-08-01",
            at=time(9, 30),
        )

        assert result.local_date == date(2026, 8, 1)
        # 09:30 Dublin (BST, UTC+1) on 2026-08-01 = 08:30 UTC
        assert result.logged_at == datetime(2026, 8, 1, 8, 30, tzinfo=UTC)

    def test_to_day_defaults_to_today(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal()
        make_meal_item(meal=meal, food=food)

        now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
        result = copy_meal(db_session, meal_id=meal.id, local_tz="UTC", now=now)

        assert result.local_date == date(2026, 8, 2)

    def test_at_omitted_reuses_source_time_of_day(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal(
            logged_at=datetime(2026, 7, 26, 7, 15, tzinfo=UTC),  # 08:15 Dublin (BST)
            local_tz="Europe/Dublin",
            local_date=date(2026, 7, 26),
        )
        make_meal_item(meal=meal, food=food)

        now = datetime(2026, 8, 2, 20, 0, tzinfo=UTC)
        result = copy_meal(
            db_session, meal_id=meal.id, local_tz="Europe/Dublin", to_day="today", now=now
        )

        assert result.local_date == date(2026, 8, 2)
        # Source local time-of-day (08:15 Dublin) reused on the new day.
        assert result.logged_at == datetime(2026, 8, 2, 7, 15, tzinfo=UTC)


class TestCopyMealMetaFields:
    def test_meal_type_carries_forward_from_source(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal(
            meal_type=MealType.breakfast,
            logged_at=datetime(2026, 7, 26, 20, 0, tzinfo=UTC),
        )
        make_meal_item(meal=meal, food=food)

        # The resolved copy time would infer as "dinner" if meal_type were
        # re-inferred; it must carry forward from the source instead.
        result = copy_meal(db_session, meal_id=meal.id, local_tz="UTC")

        assert result.meal_type == MealType.breakfast

    def test_notes_default_to_empty_when_omitted(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal(notes="big appetite today")
        make_meal_item(meal=meal, food=food)

        result = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin")

        assert result.notes is None

    def test_notes_explicit_value_is_used(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal(notes="original note")
        make_meal_item(meal=meal, food=food)

        result = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin", notes="new note")

        assert result.notes == "new note"


class TestCopyMealNotFound:
    def test_source_meal_not_found_raises(self, db_session: Session) -> None:
        with pytest.raises(MealNotFoundError) as exc_info:
            copy_meal(db_session, meal_id=999999, local_tz="Europe/Dublin")
        assert exc_info.value.error == "meal_not_found"


class TestCopyMealItemIds:
    def test_copied_items_have_their_own_ids(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food()
        meal = make_meal()
        item = make_meal_item(meal=meal, food=food)

        result = copy_meal(db_session, meal_id=meal.id, local_tz="Europe/Dublin")

        assert result.id != meal.id
        assert result.items[0].id != item.id
        assert result.items[0].id is not None
