from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import MealItemSource, MealType, QuantityUnit, get_session
from app.domain import get_day, get_range

router = APIRouter(tags=["day"])
DbSession = Annotated[Session, Depends(get_session)]


# --- Pydantic response schemas ------------------------------------------------


class ItemMacrosSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None


class MealItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_id: int | None = None
    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    source: MealItemSource
    macros: ItemMacrosSchema


class DayMealGroupSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    logged_at: str
    meal_type: MealType
    notes: str | None = None
    items: list[MealItemSchema]
    totals: ItemMacrosSchema


class EffectiveTargetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    effective_from: date
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    calories_out: int | None = None
    effective_calories: int


class EnergyPointSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    balance: int


class EnergyEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    at: datetime
    delta_kcal: int
    kind: Literal["meal", "workout"]
    status: Literal["planned", "completed"] | None = None


class FuelingFlagSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workout_id: int
    at: datetime
    status: Literal["well_fueled", "under_fueled"]


class EnergyTimelineSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    points: list[EnergyPointSchema]
    forecast_points: list[EnergyPointSchema]
    events: list[EnergyEventSchema]
    current_balance: int
    predicted_end_of_day: int
    end_of_day_target: int
    fueling_flags: list[FuelingFlagSchema]


class DayResponseSchema(BaseModel):
    date: date
    meals: dict[str, list[DayMealGroupSchema]]
    day_totals: ItemMacrosSchema
    effective_target: EffectiveTargetSchema | None = None
    delta_vs_target: ItemMacrosSchema | None = None
    energy: EnergyTimelineSchema | None = None


class PeriodTotalsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_start: date
    period_end: date
    totals: ItemMacrosSchema
    effective_target: EffectiveTargetSchema | None = None
    adherence: bool | None = None


class RangeResponseSchema(BaseModel):
    from_date: date
    to_date: date
    granularity: str
    periods: list[PeriodTotalsSchema]


# --- Routes -------------------------------------------------------------------


@router.get("/api/day/{day}", response_model=DayResponseSchema)
def read_day(
    session: DbSession,
    day: Annotated[date, Path(description="Local date (YYYY-MM-DD)")],
) -> DayResponseSchema:
    result = get_day(session, day=day)

    # Convert MealType enum keys to string for JSON serialization
    meals_dict: dict[str, list[DayMealGroupSchema]] = {}
    for meal_type, groups in result.meals.items():
        meals_dict[meal_type.value] = [
            DayMealGroupSchema(
                id=g.id,
                logged_at=g.logged_at.isoformat(),
                meal_type=g.meal_type,
                notes=g.notes,
                items=[
                    MealItemSchema(
                        id=item.id,
                        food_id=item.food_id,
                        name=item.name,
                        quantity=item.quantity,
                        quantity_unit=item.quantity_unit,
                        source=item.source,
                        macros=ItemMacrosSchema.model_validate(item.macros, from_attributes=True),
                    )
                    for item in g.items
                ],
                totals=ItemMacrosSchema.model_validate(g.totals, from_attributes=True),
            )
            for g in groups
        ]

    return DayResponseSchema(
        date=result.date,
        meals=meals_dict,
        day_totals=ItemMacrosSchema.model_validate(result.day_totals, from_attributes=True),
        effective_target=(
            EffectiveTargetSchema.model_validate(result.effective_target, from_attributes=True)
            if result.effective_target is not None
            else None
        ),
        delta_vs_target=(
            ItemMacrosSchema.model_validate(result.delta_vs_target, from_attributes=True)
            if result.delta_vs_target is not None
            else None
        ),
        energy=(
            EnergyTimelineSchema.model_validate(result.energy, from_attributes=True)
            if result.energy is not None
            else None
        ),
    )


@router.get("/api/range", response_model=RangeResponseSchema)
def read_range(
    session: DbSession,
    from_date: Annotated[date, Query(alias="from", description="Start date (inclusive)")],
    to_date: Annotated[date, Query(alias="to", description="End date (inclusive)")],
    granularity: Annotated[str, Query(description="'day' or 'week'")] = "day",
) -> RangeResponseSchema:
    if granularity not in ("day", "week"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="granularity must be 'day' or 'week'",
        )

    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must not be after 'to'",
        )

    result = get_range(session, from_date=from_date, to_date=to_date, granularity=granularity)

    return RangeResponseSchema(
        from_date=result.from_date,
        to_date=result.to_date,
        granularity=result.granularity,
        periods=[
            PeriodTotalsSchema(
                period_start=p.period_start,
                period_end=p.period_end,
                totals=ItemMacrosSchema.model_validate(p.totals, from_attributes=True),
                effective_target=(
                    EffectiveTargetSchema.model_validate(p.effective_target, from_attributes=True)
                    if p.effective_target is not None
                    else None
                ),
                adherence=p.adherence,
            )
            for p in result.periods
        ],
    )
