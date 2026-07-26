"""Tests for T-026: Templates domain.

Covers create_template, update_template, delete_template, list_templates,
and log_template. The acceptance test verifies that editing a template does
NOT modify already-logged meals (byte-for-byte unchanged).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import Food, MealItem, MealItemSource, QuantityUnit, ServingUnit
from app.domain import (
    TemplateItemSpec,
    TemplateNotFoundError,
    create_template,
    delete_template,
    list_templates,
    log_template,
    update_template,
)


@pytest.fixture
def frozen_logged_at() -> datetime:
    return datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def dublin_tz() -> str:
    return "Europe/Dublin"


@pytest.fixture
def sample_food(db_session: Session) -> Food:
    food = Food(
        name="Oats",
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        calories=Decimal("389"),
        protein_g=Decimal("16.7"),
        carbs_g=Decimal("66.3"),
        fat_g=Decimal("6.9"),
    )
    db_session.add(food)
    db_session.flush()
    return food


class TestCreateTemplate:
    def test_create_with_food_backed_item(self, db_session: Session, sample_food: Food) -> None:
        result = create_template(
            db_session,
            name="Morning Oats",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("80"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
            ],
        )

        assert result.id is not None
        assert result.name == "Morning Oats"
        assert len(result.items) == 1
        assert result.items[0].food_id == sample_food.id
        assert result.items[0].quantity == Decimal("80")
        assert result.items[0].calories is None  # food-backed, no stored macros

    def test_create_with_adhoc_item(self, db_session: Session) -> None:
        result = create_template(
            db_session,
            name="Quick Snack",
            items=[
                TemplateItemSpec(
                    name="Homemade granola",
                    quantity=Decimal("50"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("220"),
                    protein_g=Decimal("5"),
                    carbs_g=Decimal("30"),
                    fat_g=Decimal("10"),
                ),
            ],
        )

        assert result.id is not None
        assert len(result.items) == 1
        item = result.items[0]
        assert item.food_id is None
        assert item.calories == Decimal("220")
        assert item.protein_g == Decimal("5")

    def test_create_with_mixed_items(self, db_session: Session, sample_food: Food) -> None:
        result = create_template(
            db_session,
            name="Mixed Template",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("80"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
                TemplateItemSpec(
                    name="Honey drizzle",
                    quantity=Decimal("15"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("46"),
                    protein_g=Decimal("0"),
                    carbs_g=Decimal("12.5"),
                    fat_g=Decimal("0"),
                ),
            ],
        )

        assert len(result.items) == 2


class TestUpdateTemplate:
    def test_update_name(self, db_session: Session, sample_food: Food) -> None:
        template = create_template(
            db_session,
            name="Old Name",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("80"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
            ],
        )

        updated = update_template(db_session, template_id=template.id, name="New Name")
        assert updated.name == "New Name"
        assert len(updated.items) == 1  # Items unchanged

    def test_update_items_replaces_all(self, db_session: Session, sample_food: Food) -> None:
        template = create_template(
            db_session,
            name="Test",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("80"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
            ],
        )

        updated = update_template(
            db_session,
            template_id=template.id,
            items=[
                TemplateItemSpec(
                    name="Big Oats",
                    quantity=Decimal("120"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
                TemplateItemSpec(
                    name="Milk",
                    quantity=Decimal("200"),
                    quantity_unit=QuantityUnit.ml,
                    calories=Decimal("100"),
                    protein_g=Decimal("7"),
                    carbs_g=Decimal("10"),
                    fat_g=Decimal("4"),
                ),
            ],
        )

        assert len(updated.items) == 2
        assert updated.items[0].name == "Big Oats"
        assert updated.items[0].quantity == Decimal("120")

    def test_update_not_found_raises(self, db_session: Session) -> None:
        with pytest.raises(TemplateNotFoundError):
            update_template(db_session, template_id=99999, name="Nope")


class TestDeleteTemplate:
    def test_soft_delete(self, db_session: Session) -> None:
        template = create_template(
            db_session,
            name="To Delete",
            items=[
                TemplateItemSpec(
                    name="Item",
                    quantity=Decimal("100"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("100"),
                    protein_g=Decimal("5"),
                    carbs_g=Decimal("10"),
                    fat_g=Decimal("3"),
                ),
            ],
        )

        deleted = delete_template(db_session, template_id=template.id)
        assert deleted.deleted_at is not None

    def test_deleted_template_not_in_list(self, db_session: Session) -> None:
        template = create_template(
            db_session,
            name="Will Be Deleted",
            items=[
                TemplateItemSpec(
                    name="Item",
                    quantity=Decimal("100"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("100"),
                    protein_g=Decimal("5"),
                    carbs_g=Decimal("10"),
                    fat_g=Decimal("3"),
                ),
            ],
        )

        delete_template(db_session, template_id=template.id)
        templates = list_templates(db_session)
        assert all(t.id != template.id for t in templates)

    def test_delete_not_found_raises(self, db_session: Session) -> None:
        with pytest.raises(TemplateNotFoundError):
            delete_template(db_session, template_id=99999)


class TestListTemplates:
    def test_list_returns_items(self, db_session: Session, sample_food: Food) -> None:
        create_template(
            db_session,
            name="Template A",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("80"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
            ],
        )
        create_template(
            db_session,
            name="Template B",
            items=[
                TemplateItemSpec(
                    name="Snack",
                    quantity=Decimal("50"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("100"),
                    protein_g=Decimal("3"),
                    carbs_g=Decimal("15"),
                    fat_g=Decimal("4"),
                ),
            ],
        )

        templates = list_templates(db_session)
        assert len(templates) >= 2
        names = [t.name for t in templates]
        assert "Template A" in names
        assert "Template B" in names


class TestLogTemplate:
    def test_log_food_backed_items(
        self,
        db_session: Session,
        sample_food: Food,
        frozen_logged_at: datetime,
        dublin_tz: str,
    ) -> None:
        template = create_template(
            db_session,
            name="Oats Breakfast",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("80"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
            ],
        )

        meal = log_template(
            db_session,
            template_id=template.id,
            logged_at=frozen_logged_at,
            local_tz=dublin_tz,
            meal_type="breakfast",
        )

        assert meal.id is not None
        assert len(meal.items) == 1
        item = meal.items[0]
        assert item.food_id == sample_food.id
        assert item.source == MealItemSource.template
        assert item.quantity == Decimal("80")
        # Macros computed from food: 389 * 80/100
        assert item.macros.calories == Decimal("311.2")

    def test_log_adhoc_items(
        self,
        db_session: Session,
        frozen_logged_at: datetime,
        dublin_tz: str,
    ) -> None:
        template = create_template(
            db_session,
            name="Snack Template",
            items=[
                TemplateItemSpec(
                    name="Granola",
                    quantity=Decimal("50"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("220"),
                    protein_g=Decimal("5"),
                    carbs_g=Decimal("30"),
                    fat_g=Decimal("10"),
                ),
            ],
        )

        meal = log_template(
            db_session,
            template_id=template.id,
            logged_at=frozen_logged_at,
            local_tz=dublin_tz,
        )

        assert len(meal.items) == 1
        item = meal.items[0]
        assert item.food_id is None
        assert item.source == MealItemSource.template
        assert item.macros.calories == Decimal("220")

    def test_log_with_quantity_scale(
        self,
        db_session: Session,
        frozen_logged_at: datetime,
        dublin_tz: str,
    ) -> None:
        """quantity_scale multiplies all items uniformly."""
        template = create_template(
            db_session,
            name="Scalable",
            items=[
                TemplateItemSpec(
                    name="Estimate item",
                    quantity=Decimal("100"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("200"),
                    protein_g=Decimal("10"),
                    carbs_g=Decimal("20"),
                    fat_g=Decimal("8"),
                ),
            ],
        )

        meal = log_template(
            db_session,
            template_id=template.id,
            logged_at=frozen_logged_at,
            local_tz=dublin_tz,
            quantity_scale=Decimal("0.5"),
        )

        item = meal.items[0]
        assert item.quantity == Decimal("50")  # 100 * 0.5
        assert item.macros.calories == Decimal("100")  # 200 * 0.5
        assert item.macros.protein_g == Decimal("5")  # 10 * 0.5

    def test_log_not_found_raises(
        self,
        db_session: Session,
        frozen_logged_at: datetime,
        dublin_tz: str,
    ) -> None:
        with pytest.raises(TemplateNotFoundError):
            log_template(
                db_session,
                template_id=99999,
                logged_at=frozen_logged_at,
                local_tz=dublin_tz,
            )

    def test_log_deleted_template_raises(
        self,
        db_session: Session,
        frozen_logged_at: datetime,
        dublin_tz: str,
    ) -> None:
        template = create_template(
            db_session,
            name="Deleted",
            items=[
                TemplateItemSpec(
                    name="Item",
                    quantity=Decimal("100"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("100"),
                    protein_g=Decimal("5"),
                    carbs_g=Decimal("10"),
                    fat_g=Decimal("3"),
                ),
            ],
        )
        delete_template(db_session, template_id=template.id)

        with pytest.raises(TemplateNotFoundError):
            log_template(
                db_session,
                template_id=template.id,
                logged_at=frozen_logged_at,
                local_tz=dublin_tz,
            )


class TestTemplateEditDoesNotTouchPastMeals:
    """Acceptance test: log a template, edit the template, verify the
    historical meal is byte-for-byte unchanged.
    """

    def test_edit_template_historical_meal_unchanged(
        self,
        db_session: Session,
        sample_food: Food,
        frozen_logged_at: datetime,
        dublin_tz: str,
    ) -> None:
        """Log a template, edit it, assert past meal is unchanged."""

        # Create template with food-backed + ad-hoc items
        template = create_template(
            db_session,
            name="Original Template",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("80"),
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
                TemplateItemSpec(
                    name="Honey",
                    quantity=Decimal("15"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("46"),
                    protein_g=Decimal("0"),
                    carbs_g=Decimal("12.5"),
                    fat_g=Decimal("0"),
                ),
            ],
        )

        # Log the template as a meal
        meal = log_template(
            db_session,
            template_id=template.id,
            logged_at=frozen_logged_at,
            local_tz=dublin_tz,
            meal_type="breakfast",
        )
        db_session.flush()

        # Snapshot the meal items from the database
        meal_item_ids = [item.id for item in meal.items]
        original_items = []
        for item_id in meal_item_ids:
            mi = db_session.get(MealItem, item_id)
            original_items.append(
                {
                    "id": mi.id,
                    "meal_id": mi.meal_id,
                    "food_id": mi.food_id,
                    "name": mi.name,
                    "quantity": mi.quantity,
                    "quantity_unit": mi.quantity_unit,
                    "calories": mi.calories,
                    "protein_g": mi.protein_g,
                    "carbs_g": mi.carbs_g,
                    "fat_g": mi.fat_g,
                    "fiber_g": mi.fiber_g,
                    "sat_fat_g": mi.sat_fat_g,
                    "sodium_mg": mi.sodium_mg,
                    "source": mi.source,
                }
            )

        # Now edit the template: change quantity, add item, change name
        update_template(
            db_session,
            template_id=template.id,
            name="Modified Template",
            items=[
                TemplateItemSpec(
                    name="Oats",
                    quantity=Decimal("120"),  # Changed from 80 to 120
                    quantity_unit=QuantityUnit.g,
                    food_id=sample_food.id,
                ),
                TemplateItemSpec(
                    name="Honey",
                    quantity=Decimal("25"),  # Changed from 15 to 25
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("77"),  # Changed
                    protein_g=Decimal("0"),
                    carbs_g=Decimal("20.8"),  # Changed
                    fat_g=Decimal("0"),
                ),
                TemplateItemSpec(
                    name="Berries",
                    quantity=Decimal("50"),
                    quantity_unit=QuantityUnit.g,
                    calories=Decimal("25"),
                    protein_g=Decimal("0.5"),
                    carbs_g=Decimal("6"),
                    fat_g=Decimal("0.1"),
                ),
            ],
        )
        db_session.flush()

        # Verify the historical meal items are byte-for-byte unchanged
        for i, item_id in enumerate(meal_item_ids):
            mi = db_session.get(MealItem, item_id)
            assert mi is not None, f"Meal item {item_id} was deleted"
            assert mi.id == original_items[i]["id"]
            assert mi.meal_id == original_items[i]["meal_id"]
            assert mi.food_id == original_items[i]["food_id"]
            assert mi.name == original_items[i]["name"]
            assert mi.quantity == original_items[i]["quantity"]
            assert mi.quantity_unit == original_items[i]["quantity_unit"]
            assert mi.calories == original_items[i]["calories"]
            assert mi.protein_g == original_items[i]["protein_g"]
            assert mi.carbs_g == original_items[i]["carbs_g"]
            assert mi.fat_g == original_items[i]["fat_g"]
            assert mi.fiber_g == original_items[i]["fiber_g"]
            assert mi.sat_fat_g == original_items[i]["sat_fat_g"]
            assert mi.sodium_mg == original_items[i]["sodium_mg"]
            assert mi.source == original_items[i]["source"]
