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
class EffectiveTarget:
    """Effective target for a day with base + calories_out breakdown."""

    base_calories: int
    calories_out: int | None
    effective_calories: Decimal
    protein_g: int
    carbs_g: int
    fat_g: int


@dataclass(frozen=True, slots=True)
class DayMealGroup:
    """A meal with computed items and totals, for the day view."""

    id: int
    logged_at: datetime
    meal_type: MealType
    notes: str | None
    items: list[MealItemResponse]
    totals: ItemMacros


@dataclass(frozen=True, slots=True)
class DayResponse:
    """Full day aggregation: meals grouped by type, totals, target, delta."""

    date: date
    meals: dict[MealType, list[DayMealGroup]]
    day_totals: ItemMacros
    effective_target: EffectiveTarget | None
    delta_vs_target: ItemMacros | None


@dataclass(frozen=True, slots=True)
class PeriodTotals:
    """Per-period totals for range aggregation."""

    period_start: date
    period_end: date
    totals: ItemMacros
    effective_target: EffectiveTarget | None
    adherence: bool | None  # None if no target; True if calories <= effective target


@dataclass(frozen=True, slots=True)
class RangeResponse:
    """Range aggregation with per-period totals and targets."""

    from_date: date
    to_date: date
    granularity: str  # "day" or "week"
    periods: list[PeriodTotals]
