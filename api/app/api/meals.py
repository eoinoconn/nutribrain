from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import MealItemSource, MealType, QuantityUnit, get_session
from app.domain import (
    MealItemSpec,
    MealResponse,
    delete_meal,
    delete_meal_item,
    log_meal,
)

router = APIRouter(tags=["meals"])
DbSession = Annotated[Session, Depends(get_session)]


# --- Request / Response schemas --------------------------------------------


class MealItemRequest(BaseModel):
    name: str
    quantity: Decimal = Field(gt=0)
    quantity_unit: QuantityUnit
    food_id: int | None = None
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None


class CreateMealRequest(BaseModel):
    items: list[MealItemRequest] = Field(min_length=1)
    logged_at: datetime
    local_tz: str
    meal_type: str | None = None
    notes: str | None = None


class ItemMacrosResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


class MealItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_id: int | None
    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    source: MealItemSource
    macros: ItemMacrosResponse


class CreateMealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    logged_at: datetime
    local_tz: str
    local_date: str
    meal_type: MealType
    notes: str | None
    items: list[MealItemOut]
    totals: ItemMacrosResponse
    delta_vs_target: ItemMacrosResponse | None


class DeleteResponse(BaseModel):
    deleted: bool


# --- Routes ----------------------------------------------------------------


@router.post("/api/meals", response_model=CreateMealResponse, status_code=status.HTTP_201_CREATED)
def create_meal(
    payload: CreateMealRequest,
    session: DbSession,
) -> CreateMealResponse:
    item_specs = [
        MealItemSpec(
            name=item.name,
            quantity=item.quantity,
            quantity_unit=item.quantity_unit,
            food_id=item.food_id,
            calories=item.calories,
            protein_g=item.protein_g,
            carbs_g=item.carbs_g,
            fat_g=item.fat_g,
            fiber_g=item.fiber_g,
            sat_fat_g=item.sat_fat_g,
            sodium_mg=item.sodium_mg,
        )
        for item in payload.items
    ]

    result: MealResponse = log_meal(
        session,
        items=item_specs,
        logged_at=payload.logged_at,
        local_tz=payload.local_tz,
        meal_type=payload.meal_type,
        notes=payload.notes,
    )

    return CreateMealResponse(
        id=result.id,
        logged_at=result.logged_at,
        local_tz=result.local_tz,
        local_date=result.local_date.isoformat(),
        meal_type=result.meal_type,
        notes=result.notes,
        items=[
            MealItemOut(
                id=item.id,
                food_id=item.food_id,
                name=item.name,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                source=item.source,
                macros=ItemMacrosResponse(
                    calories=item.macros.calories,
                    protein_g=item.macros.protein_g,
                    carbs_g=item.macros.carbs_g,
                    fat_g=item.macros.fat_g,
                    fiber_g=item.macros.fiber_g,
                    sat_fat_g=item.macros.sat_fat_g,
                    sodium_mg=item.macros.sodium_mg,
                ),
            )
            for item in result.items
        ],
        totals=ItemMacrosResponse(
            calories=result.totals.calories,
            protein_g=result.totals.protein_g,
            carbs_g=result.totals.carbs_g,
            fat_g=result.totals.fat_g,
            fiber_g=result.totals.fiber_g,
            sat_fat_g=result.totals.sat_fat_g,
            sodium_mg=result.totals.sodium_mg,
        ),
        delta_vs_target=ItemMacrosResponse(
            calories=result.delta_vs_target.calories,
            protein_g=result.delta_vs_target.protein_g,
            carbs_g=result.delta_vs_target.carbs_g,
            fat_g=result.delta_vs_target.fat_g,
            fiber_g=result.delta_vs_target.fiber_g,
            sat_fat_g=result.delta_vs_target.sat_fat_g,
            sodium_mg=result.delta_vs_target.sodium_mg,
        )
        if result.delta_vs_target is not None
        else None,
    )


@router.delete("/api/meals/{meal_id}", response_model=DeleteResponse)
def remove_meal(
    meal_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> DeleteResponse:
    delete_meal(session, meal_id=meal_id)
    return DeleteResponse(deleted=True)


@router.delete("/api/meal-items/{item_id}", response_model=DeleteResponse)
def remove_meal_item(
    item_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> DeleteResponse:
    delete_meal_item(session, item_id=item_id)
    return DeleteResponse(deleted=True)
