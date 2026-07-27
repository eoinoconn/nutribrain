"""Shared MCP serializers matching HTTP DTO shapes.

MCP tools and HTTP routes should present one canonical shape for each business
object so clients do not need adapter-specific parsing.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.api.foods import FoodResponse, FoodSearchResponse
from app.db import MealType, QuantityUnit
from app.domain.dto import (
    DayMealGroup,
    DayResponse,
    EffectiveTarget,
    ItemMacros,
    MealItemResponse,
    MealResponse,
    PeriodTotals,
    RangeResponse,
    SetTargetResult,
    SyncIntervalsResult,
    TemplateItemResponse,
    TemplateResponse,
)
from app.domain.errors import DomainError
from app.domain.foods import FoodSearchResult


class ToolErrorResponse(BaseModel):
    """Appendix C error envelope for MCP tool responses."""

    error: str
    message: str
    candidates: list[dict[str, object]] | None = None


class ItemMacrosModel(BaseModel):
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


class MealItemModel(BaseModel):
    id: int
    food_id: int | None
    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    source: str
    macros: ItemMacrosModel


class MealModel(BaseModel):
    id: int
    logged_at: datetime
    local_tz: str
    local_date: date
    meal_type: MealType
    notes: str | None
    items: list[MealItemModel]
    totals: ItemMacrosModel
    delta_vs_target: ItemMacrosModel | None


class TemplateItemModel(BaseModel):
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


class TemplateModel(BaseModel):
    id: int
    name: str
    created_at: datetime
    deleted_at: datetime | None
    items: list[TemplateItemModel]


class EffectiveTargetModel(BaseModel):
    effective_from: date
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    calories_out: int | None
    effective_calories: int


class SetTargetResultModel(BaseModel):
    id: int
    effective_from: date
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    same_day_overlap: bool


class DayMealGroupModel(BaseModel):
    id: int
    logged_at: datetime
    meal_type: MealType
    notes: str | None
    items: list[MealItemModel]
    totals: ItemMacrosModel


class DayModel(BaseModel):
    date: date
    meals: dict[MealType, list[DayMealGroupModel]]
    day_totals: ItemMacrosModel
    effective_target: EffectiveTargetModel | None
    delta_vs_target: ItemMacrosModel | None


class PeriodTotalsModel(BaseModel):
    period_start: date
    period_end: date
    totals: ItemMacrosModel
    effective_target: EffectiveTargetModel | None
    adherence: bool | None


class RangeModel(BaseModel):
    from_date: date
    to_date: date
    granularity: Literal["day", "week"]
    periods: list[PeriodTotalsModel]


class DeleteResultModel(BaseModel):
    deleted: bool


class SyncIntervalsResultModel(BaseModel):
    from_date: date
    to_date: date
    days_synced: int
    failures: list[dict[str, object]]


class ToolResultEnvelope(BaseModel):
    """Optional envelope for tools that can return either data or error."""

    model_config = ConfigDict(extra="forbid")

    data: dict[str, Any] | None = None
    error: ToolErrorResponse | None = None


def serialize_domain_error(error: DomainError) -> ToolErrorResponse:
    return ToolErrorResponse(
        error=error.error,
        message=error.message,
        candidates=error.candidates,
    )


def serialize_macros(value: ItemMacros) -> ItemMacrosModel:
    return ItemMacrosModel(
        calories=value.calories,
        protein_g=value.protein_g,
        carbs_g=value.carbs_g,
        fat_g=value.fat_g,
        fiber_g=value.fiber_g,
        sat_fat_g=value.sat_fat_g,
        sodium_mg=value.sodium_mg,
    )


def serialize_meal_item(value: MealItemResponse) -> MealItemModel:
    return MealItemModel(
        id=value.id,
        food_id=value.food_id,
        name=value.name,
        quantity=value.quantity,
        quantity_unit=value.quantity_unit,
        source=value.source.value,
        macros=serialize_macros(value.macros),
    )


def serialize_meal(value: MealResponse) -> MealModel:
    return MealModel(
        id=value.id,
        logged_at=value.logged_at,
        local_tz=value.local_tz,
        local_date=value.local_date,
        meal_type=value.meal_type,
        notes=value.notes,
        items=[serialize_meal_item(item) for item in value.items],
        totals=serialize_macros(value.totals),
        delta_vs_target=(
            serialize_macros(value.delta_vs_target) if value.delta_vs_target is not None else None
        ),
    )


def serialize_template_item(value: TemplateItemResponse) -> TemplateItemModel:
    return TemplateItemModel(
        id=value.id,
        food_id=value.food_id,
        name=value.name,
        quantity=value.quantity,
        quantity_unit=value.quantity_unit,
        calories=value.calories,
        protein_g=value.protein_g,
        carbs_g=value.carbs_g,
        fat_g=value.fat_g,
        fiber_g=value.fiber_g,
        sat_fat_g=value.sat_fat_g,
        sodium_mg=value.sodium_mg,
    )


def serialize_template(value: TemplateResponse) -> TemplateModel:
    return TemplateModel(
        id=value.id,
        name=value.name,
        created_at=value.created_at,
        deleted_at=value.deleted_at,
        items=[serialize_template_item(item) for item in value.items],
    )


def serialize_effective_target(value: EffectiveTarget) -> EffectiveTargetModel:
    return EffectiveTargetModel(
        effective_from=value.effective_from,
        base_calories=value.base_calories,
        protein_g=value.protein_g,
        carbs_g=value.carbs_g,
        fat_g=value.fat_g,
        calories_out=value.calories_out,
        effective_calories=value.effective_calories,
    )


def serialize_set_target_result(value: SetTargetResult) -> SetTargetResultModel:
    return SetTargetResultModel(
        id=value.id,
        effective_from=value.effective_from,
        base_calories=value.base_calories,
        protein_g=value.protein_g,
        carbs_g=value.carbs_g,
        fat_g=value.fat_g,
        same_day_overlap=value.same_day_overlap,
    )


def serialize_day_meal_group(value: DayMealGroup) -> DayMealGroupModel:
    return DayMealGroupModel(
        id=value.id,
        logged_at=value.logged_at,
        meal_type=value.meal_type,
        notes=value.notes,
        items=[serialize_meal_item(item) for item in value.items],
        totals=serialize_macros(value.totals),
    )


def serialize_day(value: DayResponse) -> DayModel:
    return DayModel(
        date=value.date,
        meals={
            meal_type: [serialize_day_meal_group(group) for group in groups]
            for meal_type, groups in value.meals.items()
        },
        day_totals=serialize_macros(value.day_totals),
        effective_target=(
            serialize_effective_target(value.effective_target)
            if value.effective_target is not None
            else None
        ),
        delta_vs_target=(
            serialize_macros(value.delta_vs_target) if value.delta_vs_target is not None else None
        ),
    )


def serialize_period_totals(value: PeriodTotals) -> PeriodTotalsModel:
    return PeriodTotalsModel(
        period_start=value.period_start,
        period_end=value.period_end,
        totals=serialize_macros(value.totals),
        effective_target=(
            serialize_effective_target(value.effective_target)
            if value.effective_target is not None
            else None
        ),
        adherence=value.adherence,
    )


def serialize_range(value: RangeResponse) -> RangeModel:
    return RangeModel(
        from_date=value.from_date,
        to_date=value.to_date,
        granularity=value.granularity,  # type: ignore[arg-type]
        periods=[serialize_period_totals(period) for period in value.periods],
    )


def serialize_sync_result(value: SyncIntervalsResult) -> SyncIntervalsResultModel:
    return SyncIntervalsResultModel(
        from_date=value.from_date,
        to_date=value.to_date,
        days_synced=value.days_synced,
        failures=value.failures,
    )


def serialize_food_search_result(value: FoodSearchResult) -> FoodSearchResponse:
    return FoodSearchResponse(
        **FoodResponse.model_validate(value.food).model_dump(),
        last_logged_at=value.last_logged_at,
        logged_count=value.logged_count,
    )
