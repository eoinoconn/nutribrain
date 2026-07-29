"""Mutation-rule regression suite (T-100).

This module exists solely to defend the propagation rules in CLAUDE.md / spec
§3. It must keep failing loudly if a future change turns read-time
computation into write-time snapshots, or loosens what is allowed to
propagate. Each test maps to one bullet of the "Mutation rules — critical"
section:

- Food edits propagate to past meals (macros, serving_size, name).
- Editing food.serving_unit is forbidden.
- meal_item edits (quantity, food_id, ad-hoc macros) stay local to that item.
- Template edits don't touch past meals; deleting a template is soft.
- Soft-deleted foods stay resolvable from historical meals but are
  unfindable in search.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import Food, QuantityUnit, ServingUnit
from app.domain.day_aggregation import get_day
from app.domain.dto import TemplateItemSpec
from app.domain.errors import ServingUnitImmutableError
from app.domain.food_resolution import resolve_food
from app.domain.foods import delete_food, search_foods, update_food
from app.domain.templates import delete_template, log_template, update_template


class TestFoodEditsPropagate:
    """Editing a food's macros, serving_size, or name recomputes past meals."""

    @pytest.mark.parametrize(
        "field,new_value",
        [
            ("calories", Decimal("999")),
            ("protein_g", Decimal("55")),
            ("carbs_g", Decimal("77")),
            ("fat_g", Decimal("33")),
            ("fiber_g", Decimal("9")),
            ("sat_fat_g", Decimal("4")),
            ("sodium_mg", Decimal("500")),
        ],
    )
    def test_macro_edit_propagates_to_past_meal(
        self, db_session: Session, make_food, make_meal, make_meal_item, field, new_value
    ):
        food = make_food(
            calories=Decimal("100"),
            protein_g=Decimal("10"),
            carbs_g=Decimal("20"),
            fat_g=Decimal("8"),
            fiber_g=Decimal("2"),
            sat_fat_g=Decimal("1"),
            sodium_mg=Decimal("50"),
        )
        meal = make_meal(local_date=datetime(2026, 1, 1, tzinfo=UTC).date())
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        update_food(session=db_session, food_id=food.id, **{field: new_value})

        after = get_day(db_session, day=meal.local_date)
        item_macros = after.meals[meal.meal_type][0].items[0].macros

        # 100g quantity == food.serving_size, so factor is 1: the item macro
        # equals the new food value directly.
        assert getattr(item_macros, field) == new_value

    def test_serving_size_edit_propagates_as_rate_change(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        """serving_size changes cal/g, so past meals recompute (§3)."""

        food = make_food(serving_size=Decimal("100"), calories=Decimal("200"))
        meal = make_meal()
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        result = get_day(db_session, day=meal.local_date)
        assert result.day_totals.calories == Decimal("200")

        # Halve serving_size: cal/g doubles, so the same 100g now reads as 400.
        update_food(session=db_session, food_id=food.id, serving_size=Decimal("50"))

        result = get_day(db_session, day=meal.local_date)
        assert result.day_totals.calories == Decimal("400")

    def test_name_edit_is_cosmetic_and_propagates_freely(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        food = make_food(name="Old Name", calories=Decimal("150"))
        meal = make_meal()
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        result = update_food(session=db_session, food_id=food.id, name="New Name")

        assert result.food.name == "New Name"
        # Macros are untouched by a name-only edit.
        after = get_day(db_session, day=meal.local_date)
        assert after.day_totals.calories == Decimal("150")

    def test_update_food_reports_affected_meal_count(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        food = make_food(calories=Decimal("100"))
        meal_a = make_meal()
        meal_b = make_meal()
        make_meal_item(meal_id=meal_a.id, food=food)
        make_meal_item(meal_id=meal_b.id, food=food)

        result = update_food(session=db_session, food_id=food.id, calories=Decimal("120"))

        assert result.affected_meals_count == 2


class TestServingUnitImmutable:
    """Editing food.serving_unit must be rejected outright."""

    def test_serving_unit_change_is_rejected(self, db_session: Session, make_food):
        food = make_food(serving_unit=ServingUnit.g)

        with pytest.raises(ServingUnitImmutableError):
            update_food(session=db_session, food_id=food.id, serving_unit=ServingUnit.piece)

        # Nothing was written.
        refreshed = db_session.get(Food, food.id)
        assert refreshed.serving_unit == ServingUnit.g


class TestMealItemEditsStayLocal:
    """quantity, food_id, and ad-hoc macro edits affect only that meal_item."""

    def test_quantity_edit_affects_only_that_item(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        food = make_food(calories=Decimal("100"))  # 100 cal per 100g
        meal_a = make_meal(local_date=datetime(2026, 1, 1, tzinfo=UTC).date())
        meal_b = make_meal(local_date=datetime(2026, 1, 2, tzinfo=UTC).date())
        item_a = make_meal_item(meal_id=meal_a.id, food=food, quantity=Decimal("100"))
        make_meal_item(meal_id=meal_b.id, food=food, quantity=Decimal("100"))

        item_a.quantity = Decimal("200")
        db_session.flush()

        result_a = get_day(db_session, day=meal_a.local_date)
        result_b = get_day(db_session, day=meal_b.local_date)

        assert result_a.day_totals.calories == Decimal("200")
        assert result_b.day_totals.calories == Decimal("100")

    def test_food_id_swap_affects_only_that_item(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        food_a = make_food(name="A", calories=Decimal("100"))
        food_b = make_food(name="B", calories=Decimal("300"))

        meal_1 = make_meal(local_date=datetime(2026, 1, 1, tzinfo=UTC).date())
        meal_2 = make_meal(local_date=datetime(2026, 1, 2, tzinfo=UTC).date())
        item_1 = make_meal_item(meal_id=meal_1.id, food=food_a, quantity=Decimal("100"))
        make_meal_item(meal_id=meal_2.id, food=food_a, quantity=Decimal("100"))

        item_1.food_id = food_b.id
        db_session.flush()

        result_1 = get_day(db_session, day=meal_1.local_date)
        result_2 = get_day(db_session, day=meal_2.local_date)

        assert result_1.day_totals.calories == Decimal("300")
        assert result_2.day_totals.calories == Decimal("100")

    def test_adhoc_macro_edit_affects_only_that_item(
        self, db_session: Session, make_meal, make_meal_item
    ):
        meal_a = make_meal(local_date=datetime(2026, 1, 1, tzinfo=UTC).date())
        meal_b = make_meal(local_date=datetime(2026, 1, 2, tzinfo=UTC).date())
        item_a = make_meal_item(
            meal_id=meal_a.id,
            food_id=None,
            calories=Decimal("400"),
            protein_g=Decimal("20"),
            carbs_g=Decimal("50"),
            fat_g=Decimal("15"),
        )
        make_meal_item(
            meal_id=meal_b.id,
            food_id=None,
            calories=Decimal("400"),
            protein_g=Decimal("20"),
            carbs_g=Decimal("50"),
            fat_g=Decimal("15"),
        )

        item_a.calories = Decimal("999")
        db_session.flush()

        result_a = get_day(db_session, day=meal_a.local_date)
        result_b = get_day(db_session, day=meal_b.local_date)

        assert result_a.day_totals.calories == Decimal("999")
        assert result_b.day_totals.calories == Decimal("400")


class TestTemplateEditsDontTouchPastMeals:
    """Editing/deleting a template only affects future applications."""

    def test_editing_template_item_does_not_recompute_past_meal(
        self, db_session: Session, make_template, make_template_item
    ):
        template = make_template()
        make_template_item(
            template_id=template.id,
            food_id=None,
            quantity=Decimal("1"),
            calories=Decimal("300"),
            protein_g=Decimal("20"),
            carbs_g=Decimal("30"),
            fat_g=Decimal("10"),
        )

        logged_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        meal_response = log_template(
            db_session,
            template_id=template.id,
            logged_at=logged_at,
            local_tz="UTC",
        )
        assert meal_response.totals.calories == Decimal("300")

        # Now change the template's item macros.
        update_template(
            db_session,
            template_id=template.id,
            items=[
                TemplateItemSpec(
                    food_id=None,
                    name="Changed",
                    quantity=Decimal("1"),
                    quantity_unit=QuantityUnit.serving,
                    calories=Decimal("900"),
                    protein_g=Decimal("1"),
                    carbs_g=Decimal("1"),
                    fat_g=Decimal("1"),
                )
            ],
        )

        # The already-materialized meal is unaffected regardless.
        result = get_day(db_session, day=logged_at.date())
        assert result.day_totals.calories == Decimal("300")

    def test_deleting_template_is_soft_and_past_meals_unaffected(
        self, db_session: Session, make_food, make_template, make_template_item
    ):
        food = make_food(calories=Decimal("150"))
        template = make_template()
        make_template_item(template_id=template.id, food=food, quantity=Decimal("100"))

        logged_at = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
        log_template(db_session, template_id=template.id, logged_at=logged_at, local_tz="UTC")

        delete_template(db_session, template_id=template.id)

        # Template is soft-deleted, not gone.
        from app.db import Template

        deleted = db_session.get(Template, template.id)
        assert deleted is not None
        assert deleted.deleted_at is not None

        # Past meal materialized from it is untouched.
        result = get_day(db_session, day=logged_at.date())
        assert result.day_totals.calories == Decimal("150")


class TestSoftDeletedFoodResolution:
    """Soft-deleted foods stay resolvable from history but drop out of search."""

    def test_deleted_food_still_resolves_in_historical_meal(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        food = make_food(name="Discontinued Snack", calories=Decimal("250"))
        meal = make_meal()
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"))

        delete_food(session=db_session, food_id=food.id)

        result = get_day(db_session, day=meal.local_date)
        assert result.day_totals.calories == Decimal("250")

    def test_deleted_food_is_unfindable_in_search(self, db_session: Session, make_food):
        food = make_food(name="Discontinued Snack", calories=Decimal("250"))
        delete_food(session=db_session, food_id=food.id)

        results = search_foods(session=db_session, query="Discontinued Snack")
        assert food.id not in [r.food.id for r in results]

    def test_deleted_food_is_not_resolvable_by_id_for_new_logging(
        self, db_session: Session, make_food
    ):
        food = make_food(name="Discontinued Snack", calories=Decimal("250"))
        delete_food(session=db_session, food_id=food.id)

        from app.domain.errors import FoodNotFoundError

        with pytest.raises(FoodNotFoundError):
            resolve_food(
                db_session,
                food_id=food.id,
                name=None,
                has_supplied_macros=False,
                now=datetime.now(UTC),
            )
