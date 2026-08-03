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
    """Input spec for a single item being logged (§4).

    ``name`` is optional when ``food_id`` is set — the domain layer fills it
    in from the resolved food's current name. It is required when ``food_id``
    is None (ad-hoc items have no other source of a name).
    """

    quantity: Decimal
    quantity_unit: QuantityUnit
    name: str | None = None
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
class MealItemMatch:
    """A meal item matched by :func:`app.domain.meal_search.find_meal`.

    Carries enough context (``meal_id``, ``item_id``) to feed directly into
    ``copy_meal`` or ``update_meal_item`` without another round-trip.
    """

    meal_id: int
    item_id: int
    food_id: int | None
    logged_at: datetime
    local_date: date
    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    macros: ItemMacros


@dataclass(frozen=True, slots=True)
class TemplateItemSpec:
    """Input spec for a single template item.

    ``name`` is optional when ``food_id`` is set — the domain layer fills it
    in from the referenced food's current name. It is required when
    ``food_id`` is None (ad-hoc items have no other source of a name).
    """

    quantity: Decimal
    quantity_unit: QuantityUnit
    name: str | None = None
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


@dataclass(frozen=True, slots=True)
class EffectiveTarget:
    """Effective target for a given day with base + activity breakdown (§3, §8).

    ``calories_out`` is None when no cache row exists (distinct from 0 which
    represents a genuine rest day).  The UI uses this to distinguish
    "target 2500 (2000 base + 500 out)" from "target 2000 (no activity data)".
    """

    effective_from: date
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    calories_out: int | None
    effective_calories: int


@dataclass(frozen=True, slots=True)
class SetTargetResult:
    """Result of set_target: the new target row plus overlap info."""

    id: int
    effective_from: date
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    same_day_overlap: bool


@dataclass(frozen=True, slots=True)
class TargetRow:
    """A single target row for listing the versioned history."""

    id: int
    effective_from: date
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    created_at: datetime


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


@dataclass(frozen=True, slots=True)
class SyncIntervalsResult:
    """Result of one sync_intervals invocation (§8, T-061).

    ``days_synced`` counts days actually written (a cached ``0`` counts; a
    ``null`` day that was skipped does not). ``failures`` holds one entry per
    day whose write failed, so the rest of the range can still succeed.
    """

    from_date: date
    to_date: date
    days_synced: int
    failures: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class SyncStatus:
    """Last known sync_intervals outcome, for the dashboard's status banner (§8).

    ``last_synced_at`` is None if a sync has never run. ``last_error`` reflects
    only a total sync failure (e.g. auth/network) — per-day failures within an
    otherwise-successful sync are surfaced via that call's own result instead.
    """

    last_synced_at: datetime | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class ManualCaloriesOutResult:
    """Result of a manual calories-out override (§8 "Manual override", G5)."""

    date: date
    calories_out: int
    fetched_at: datetime
