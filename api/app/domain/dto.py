"""Small data objects shared across domain operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from app.db import (
    MealItemSource,
    MealType,
    PlannedWorkoutSource,
    PlannedWorkoutStatus,
    QuantityUnit,
)


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

    ``days_synced`` counts ``planned_workouts`` rows upserted (EC-07: the old
    same-day calories-out sum this field used to count is retired —
    ``get_effective_target`` derives ``calories_out`` from those rows at read
    time instead). ``failures`` holds one entry per row whose write failed, so
    the rest of the range can still succeed.
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


@dataclass(frozen=True, slots=True)
class PlannedWorkoutDTO:
    """A planned/completed workout row, synced or manual (EC-01/EC-04, §6).

    Mirrors the ``planned_workouts`` table 1:1. A manually-entered row
    (``source='manual'``) has ``external_id``, ``sport_type``, ``icu_joules``,
    and ``actual_calories`` all None — see the model's column comments.
    """

    id: int
    external_id: str | None
    source: PlannedWorkoutSource
    local_date: date
    start_at: datetime
    duration_minutes: int
    sport_type: str | None
    icu_joules: int | None
    estimated_calories: int | None
    actual_calories: int | None
    status: PlannedWorkoutStatus
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class AppSettingsDTO:
    """Account-level app settings singleton (§6a, EC-06).

    Single-user app, no ``user_id`` — this is the one row of settings that
    apply to the whole account. ``local_timezone`` is an IANA tz name (e.g.
    ``"Europe/Dublin"``); the energy chart (EC-05) will read it to resolve
    local-midnight bounds on days with no logged meal to infer a timezone
    from.
    """

    local_timezone: str


@dataclass(frozen=True, slots=True)
class EnergyPoint:
    """One point on the energy-balance line (EC-05, §5).

    ``balance`` is the cumulative net kcal balance (intake minus basal drain
    minus workout expenditure) at ``at``. Rounded to the nearest whole kcal
    at this DTO boundary -- intermediate accumulation is done in ``Decimal``
    inside ``compute_energy_timeline``, per ``docs/style.md``'s "round only
    at final serialization" rule, and this DTO is treated as that boundary
    for the domain function's public return value.
    """

    at: datetime
    balance: int


@dataclass(frozen=True, slots=True)
class EnergyEvent:
    """A marker on the energy chart: a meal or a workout step (EC-05, §5).

    ``status`` is only meaningful for ``kind="workout"`` (``"planned"`` or
    ``"completed"``); ``None`` for meals. ``delta_kcal`` is the signed step
    applied at ``at`` -- positive for a meal, negative for a workout.
    """

    at: datetime
    delta_kcal: int
    kind: Literal["meal", "workout"]
    status: Literal["planned", "completed"] | None


@dataclass(frozen=True, slots=True)
class FuelingFlag:
    """Fueling classification for a future planned workout (EC-05, §5).

    Evaluated at the cumulative balance immediately before the workout's own
    step is applied on the dashed/forecast line -- i.e. "how fueled are you
    going into this session," not the balance after subtracting it.
    """

    workout_id: int
    at: datetime
    status: Literal["well_fueled", "under_fueled"]


@dataclass(frozen=True, slots=True)
class EnergyTimeline:
    """Full energy-balance timeline for one local day (EC-05, §5).

    ``points`` is the solid "so far" line from local midnight to ``now``;
    ``forecast_points`` is the dashed line continuing from ``now`` to local
    end-of-day under a zero-further-intake assumption (already-logged future
    meals and future planned workouts are still included as known steps).
    """

    points: list[EnergyPoint]
    forecast_points: list[EnergyPoint]
    events: list[EnergyEvent]
    current_balance: int
    predicted_end_of_day: int
    end_of_day_target: int
    fueling_flags: list[FuelingFlag]
