"""Templates HTTP routes (T-042).

Full CRUD plus POST /api/templates/{id}/log accepting quantity_scale.
No business logic — delegates to the domain layer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import MealItemSource, MealType, QuantityUnit, get_session
from app.domain import (
    create_template,
    delete_template,
    list_templates,
    log_template,
    update_template,
)
from app.domain.dto import ItemMacros, MealResponse, TemplateItemSpec, TemplateResponse

router = APIRouter(prefix="/api/templates", tags=["templates"])
DbSession = Annotated[Session, Depends(get_session)]


# --- Request/Response schemas -----------------------------------------------


class TemplateItemRequest(BaseModel):
    name: str = Field(min_length=1)
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


class CreateTemplateRequest(BaseModel):
    name: str = Field(min_length=1)
    items: list[TemplateItemRequest]


class UpdateTemplateRequest(BaseModel):
    name: str | None = None
    items: list[TemplateItemRequest] | None = None


class LogTemplateRequest(BaseModel):
    logged_at: datetime
    local_tz: str = Field(min_length=1)
    meal_type: str | None = None
    quantity_scale: Decimal = Decimal("1")
    notes: str | None = None


class TemplateItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    deleted_at: datetime | None
    items: list[TemplateItemOut]


class MacrosOut(BaseModel):
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None


class MealItemOut(BaseModel):
    id: int
    food_id: int | None
    name: str
    quantity: Decimal
    quantity_unit: QuantityUnit
    source: MealItemSource
    macros: MacrosOut


class MealOut(BaseModel):
    id: int
    logged_at: datetime
    local_tz: str
    local_date: str
    meal_type: MealType
    notes: str | None
    items: list[MealItemOut]
    totals: MacrosOut
    delta_vs_target: MacrosOut | None


class DeleteTemplateResponse(BaseModel):
    deleted: bool


# --- Helpers ----------------------------------------------------------------


def _template_response_to_out(t: TemplateResponse) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        name=t.name,
        created_at=t.created_at,
        deleted_at=t.deleted_at,
        items=[
            TemplateItemOut(
                id=item.id,
                food_id=item.food_id,
                name=item.name,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                calories=item.calories,
                protein_g=item.protein_g,
                carbs_g=item.carbs_g,
                fat_g=item.fat_g,
                fiber_g=item.fiber_g,
                sat_fat_g=item.sat_fat_g,
                sodium_mg=item.sodium_mg,
            )
            for item in t.items
        ],
    )


def _macros_out(m: ItemMacros) -> MacrosOut:
    return MacrosOut(
        calories=m.calories,
        protein_g=m.protein_g,
        carbs_g=m.carbs_g,
        fat_g=m.fat_g,
        fiber_g=m.fiber_g,
        sat_fat_g=m.sat_fat_g,
        sodium_mg=m.sodium_mg,
    )


def _meal_response_to_out(meal: MealResponse) -> MealOut:
    return MealOut(
        id=meal.id,
        logged_at=meal.logged_at,
        local_tz=meal.local_tz,
        local_date=str(meal.local_date),
        meal_type=meal.meal_type,
        notes=meal.notes,
        items=[
            MealItemOut(
                id=item.id,
                food_id=item.food_id,
                name=item.name,
                quantity=item.quantity,
                quantity_unit=item.quantity_unit,
                source=item.source,
                macros=_macros_out(item.macros),
            )
            for item in meal.items
        ],
        totals=_macros_out(meal.totals),
        delta_vs_target=_macros_out(meal.delta_vs_target) if meal.delta_vs_target else None,
    )


def _items_to_specs(items: list[TemplateItemRequest]) -> list[TemplateItemSpec]:
    return [
        TemplateItemSpec(
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
        for item in items
    ]


# --- Routes -----------------------------------------------------------------


@router.get("", response_model=list[TemplateOut])
def list_all_templates(
    session: DbSession,
    q: Annotated[str, Query(description="Filter templates by name")] = "",
) -> list[TemplateOut]:
    results = list_templates(session, query=q)
    return [_template_response_to_out(t) for t in results]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_new_template(
    payload: CreateTemplateRequest,
    session: DbSession,
) -> TemplateOut:
    result = create_template(session, name=payload.name, items=_items_to_specs(payload.items))
    return _template_response_to_out(result)


@router.patch("/{template_id}", response_model=TemplateOut)
def patch_template(
    payload: UpdateTemplateRequest,
    template_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> TemplateOut:
    items = _items_to_specs(payload.items) if payload.items is not None else None
    result = update_template(
        session,
        template_id=template_id,
        name=payload.name,
        items=items,
    )
    return _template_response_to_out(result)


@router.delete("/{template_id}", response_model=DeleteTemplateResponse)
def remove_template(
    template_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> DeleteTemplateResponse:
    delete_template(session, template_id=template_id)
    return DeleteTemplateResponse(deleted=True)


@router.post("/{template_id}/log", response_model=MealOut, status_code=status.HTTP_201_CREATED)
def log_template_route(
    payload: LogTemplateRequest,
    template_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> MealOut:
    result = log_template(
        session,
        template_id=template_id,
        logged_at=payload.logged_at,
        local_tz=payload.local_tz,
        meal_type=payload.meal_type,
        quantity_scale=payload.quantity_scale,
        notes=payload.notes,
    )
    return _meal_response_to_out(result)
