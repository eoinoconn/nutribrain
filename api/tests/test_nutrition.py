from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.db import QuantityUnit, ServingUnit
from app.domain import ItemMacros, UnitNormalizationError, compute_item_macros, normalize_to_grams


@dataclass(frozen=True)
class FakeFood:
    serving_size: Decimal
    serving_unit: ServingUnit
    calories: Decimal = Decimal("200")
    protein_g: Decimal = Decimal("10")
    carbs_g: Decimal = Decimal("20")
    fat_g: Decimal = Decimal("8")
    fiber_g: Decimal | None = Decimal("2")
    sat_fat_g: Decimal | None = Decimal("1")
    sodium_mg: Decimal | None = Decimal("100")
    density_g_per_ml: Decimal | None = None


@dataclass(frozen=True)
class FakeMealItem:
    food_id: int | None
    quantity: Decimal
    quantity_unit: QuantityUnit
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None


_COMBINATION_CASES = [
    (quantity_unit, food_unit)
    for quantity_unit in QuantityUnit
    for food_unit in ServingUnit
]


@pytest.mark.parametrize(("quantity_unit", "food_unit"), _COMBINATION_CASES)
def test_normalize_to_grams_all_quantity_and_serving_unit_combinations(
    quantity_unit: QuantityUnit,
    food_unit: ServingUnit,
) -> None:
    serving_size = Decimal("2") if food_unit == ServingUnit.piece else Decimal("100")
    food = FakeFood(
        serving_size=serving_size,
        serving_unit=food_unit,
        density_g_per_ml=Decimal("0.8"),
    )

    should_raise = (
        (
            food_unit == ServingUnit.piece
            and quantity_unit not in {QuantityUnit.piece, QuantityUnit.serving}
        )
        or (quantity_unit == QuantityUnit.piece and food_unit != ServingUnit.piece)
    )

    if should_raise:
        with pytest.raises(UnitNormalizationError):
            normalize_to_grams(Decimal("1"), quantity_unit, food)
        return

    grams = normalize_to_grams(Decimal("1"), quantity_unit, food)
    assert grams > 0


def test_volume_density_changes_cup_grams_as_expected() -> None:
    quantity = Decimal("1")
    dense_food = FakeFood(
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        density_g_per_ml=Decimal("0.78"),
    )
    default_density_food = FakeFood(
        serving_size=Decimal("100"),
        serving_unit=ServingUnit.g,
        density_g_per_ml=None,
    )

    cup_at_078_density = normalize_to_grams(quantity, QuantityUnit.cup, dense_food)
    cup_at_default_density = normalize_to_grams(quantity, QuantityUnit.cup, default_density_food)

    assert float(cup_at_078_density) == pytest.approx(185.0, abs=1.0)
    assert float(cup_at_default_density) == pytest.approx(237.0, abs=1.0)


def test_compute_item_macros_food_backed_items_scale_from_current_food_values() -> None:
    food = FakeFood(serving_size=Decimal("100"), serving_unit=ServingUnit.g)
    item = FakeMealItem(food_id=1, quantity=Decimal("50"), quantity_unit=QuantityUnit.g)

    macros = compute_item_macros(item, food)

    assert macros == ItemMacros(
        calories=Decimal("100"),
        protein_g=Decimal("5"),
        carbs_g=Decimal("10"),
        fat_g=Decimal("4"),
        fiber_g=Decimal("1"),
        sat_fat_g=Decimal("0.5"),
        sodium_mg=Decimal("50"),
    )


def test_compute_item_macros_adhoc_items_return_stored_values() -> None:
    item = FakeMealItem(
        food_id=None,
        quantity=Decimal("1"),
        quantity_unit=QuantityUnit.serving,
        calories=Decimal("250"),
        protein_g=Decimal("12"),
        carbs_g=Decimal("30"),
        fat_g=Decimal("8"),
        fiber_g=Decimal("3"),
        sat_fat_g=Decimal("1"),
        sodium_mg=Decimal("120"),
    )

    assert compute_item_macros(item, None) == ItemMacros(
        calories=Decimal("250"),
        protein_g=Decimal("12"),
        carbs_g=Decimal("30"),
        fat_g=Decimal("8"),
        fiber_g=Decimal("3"),
        sat_fat_g=Decimal("1"),
        sodium_mg=Decimal("120"),
    )
