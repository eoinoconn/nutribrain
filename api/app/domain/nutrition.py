"""Unit normalization and read-time macro computation (T-020).

For food-backed meal items, totals are computed at read time from the current
food row so historical meals automatically reflect food edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol

from app.db import QuantityUnit, ServingUnit


class UnitNormalizationError(ValueError):
    """Raised when a quantity unit cannot be normalized for the given food."""


class SupportsFood(Protocol):
    serving_size: Decimal
    serving_unit: ServingUnit
    density_g_per_ml: Decimal | None
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


class SupportsMealItem(Protocol):
    food_id: int | None
    quantity: Decimal
    quantity_unit: QuantityUnit
    calories: Decimal | None
    protein_g: Decimal | None
    carbs_g: Decimal | None
    fat_g: Decimal | None
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


@dataclass(frozen=True, slots=True)
class ItemMacros:
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


MASS_TO_G: Final[dict[str, Decimal]] = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}

VOLUME_TO_ML: Final[dict[str, Decimal]] = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "fl_oz": Decimal("29.5735295625"),
    "tsp": Decimal("4.92892159375"),
    "tbsp": Decimal("14.78676478125"),
    "cup": Decimal("236.5882365"),
}

_DEFAULT_DENSITY: Final[Decimal] = Decimal("1")


def normalize_to_grams(
    quantity: Decimal,
    unit: QuantityUnit | ServingUnit,
    food: SupportsFood,
) -> Decimal:
    """Normalize a quantity to a common basis used for macro factor math.

    Mass and volume units convert by frozen constants; volume additionally uses
    food density (null means 1.0). `piece` and `serving` are food-specific
    units and are never guessed across foods.
    """

    unit_value = unit.value
    food_unit = food.serving_unit.value

    if unit_value in MASS_TO_G:
        if food_unit == ServingUnit.piece.value:
            raise UnitNormalizationError(
                "Mass quantities cannot be used with foods defined in pieces"
            )
        return quantity * MASS_TO_G[unit_value]

    if unit_value in VOLUME_TO_ML:
        if food_unit == ServingUnit.piece.value:
            raise UnitNormalizationError(
                "Volume quantities cannot be used with foods defined in pieces"
            )
        density = food.density_g_per_ml if food.density_g_per_ml is not None else _DEFAULT_DENSITY
        return quantity * VOLUME_TO_ML[unit_value] * density

    if unit_value == QuantityUnit.piece.value:
        if food_unit != ServingUnit.piece.value:
            raise UnitNormalizationError(
                "Piece quantities require foods whose serving_unit is piece"
            )
        # Piece-defined foods use piece counts as the comparison basis.
        return quantity

    if unit_value == QuantityUnit.serving.value:
        return quantity * normalize_to_grams(food.serving_size, food.serving_unit, food)

    raise UnitNormalizationError(f"Unsupported quantity unit: {unit_value}")


def compute_item_macros(meal_item: SupportsMealItem, food: SupportsFood | None) -> ItemMacros:
    """Compute effective macros for a meal item.

    Food-backed items are computed at read time from the current food row so
    food edits propagate to historical meals. Ad-hoc items return their stored
    macro values unchanged.
    """

    if meal_item.food_id is None:
        return ItemMacros(
            calories=_require_macro(meal_item.calories, "calories"),
            protein_g=_require_macro(meal_item.protein_g, "protein_g"),
            carbs_g=_require_macro(meal_item.carbs_g, "carbs_g"),
            fat_g=_require_macro(meal_item.fat_g, "fat_g"),
            fiber_g=meal_item.fiber_g,
            sat_fat_g=meal_item.sat_fat_g,
            sodium_mg=meal_item.sodium_mg,
        )

    if food is None:
        raise ValueError("food is required for food-backed meal items")

    grams = normalize_to_grams(meal_item.quantity, meal_item.quantity_unit, food)
    serving_grams = normalize_to_grams(food.serving_size, food.serving_unit, food)
    factor = grams / serving_grams

    return ItemMacros(
        calories=food.calories * factor,
        protein_g=food.protein_g * factor,
        carbs_g=food.carbs_g * factor,
        fat_g=food.fat_g * factor,
        fiber_g=_scale_optional(food.fiber_g, factor),
        sat_fat_g=_scale_optional(food.sat_fat_g, factor),
        sodium_mg=_scale_optional(food.sodium_mg, factor),
    )


def _scale_optional(value: Decimal | None, factor: Decimal) -> Decimal | None:
    if value is None:
        return None
    return value * factor


def _require_macro(value: Decimal | None, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"ad-hoc meal item is missing required macro: {field_name}")
    return value
