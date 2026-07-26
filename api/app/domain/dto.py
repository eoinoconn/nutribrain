"""Small data objects shared across domain operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.db import MealItemSource, MealType, QuantityUnit


@dataclass(frozen=True, slots=True)
class ItemMacros:
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


@dataclass(frozen=True, slots=True)
class FoodCandidate:
    id: int
    name: str
    calories: Decimal
    is_favorite: bool
    last_logged_at: datetime | None


@dataclass(frozen=True, slots=True)
class MealItemSpec:
    """Input spec for a single item being logged (§4)."""

    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    food_id: int | None = None
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None


@dataclass(frozen=True, slots=True)
class MealResponse:
    """Created meal with resolved items, totals, and delta (§4)."""

    id: int
    logged_at: datetime
    local_tz: str
    local_date: date
    meal_type: MealType
    notes: str | None
    items: list[MealItemResponse]
    totals: ItemMacros
    delta_vs_target: ItemMacros | None  # None if no target set


@dataclass(frozen=True, slots=True)
class MealItemResponse:
    """Resolved meal item with source."""

    id: int
    food_id: int | None
    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    source: MealItemSource
    macros: ItemMacros


@dataclass(frozen=True, slots=True)
class TemplateItemSpec:
    """Input spec for a single template item."""

    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    food_id: int | None = None
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None


@dataclass(frozen=True, slots=True)
class TemplateItemResponse:
    """A single item within a template."""

    id: int
    food_id: int | None
    name: str
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
class TemplateResponse:
    """A template with its items."""

    id: int
    name: str
    created_at: datetime
    deleted_at: datetime | None
    items: list[TemplateItemResponse]
