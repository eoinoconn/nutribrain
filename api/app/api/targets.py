from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain import get_effective_target, list_targets, set_target

router = APIRouter(prefix="/api/targets", tags=["targets"])
DbSession = Annotated[Session, Depends(get_session)]


class TargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    effective_from: date_type
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    created_at: str  # ISO datetime string


class EffectiveTargetResponse(BaseModel):
    effective_from: date_type
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    calories_out: int | None
    effective_calories: int


class CreateTargetRequest(BaseModel):
    effective_from: date_type
    base_calories: int = Field(ge=0)
    protein_g: int = Field(ge=0)
    carbs_g: int = Field(ge=0)
    fat_g: int = Field(ge=0)


class CreateTargetResponse(BaseModel):
    id: int
    effective_from: date_type
    base_calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    same_day_overlap: bool


@router.get("", response_model=list[TargetResponse])
def get_targets(session: DbSession) -> list[TargetResponse]:
    rows = list_targets(session)
    return [
        TargetResponse(
            id=r.id,
            effective_from=r.effective_from,
            base_calories=r.base_calories,
            protein_g=r.protein_g,
            carbs_g=r.carbs_g,
            fat_g=r.fat_g,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.post("", response_model=CreateTargetResponse, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: CreateTargetRequest,
    session: DbSession,
) -> CreateTargetResponse:
    result = set_target(session, **payload.model_dump())
    return CreateTargetResponse(
        id=result.id,
        effective_from=result.effective_from,
        base_calories=result.base_calories,
        protein_g=result.protein_g,
        carbs_g=result.carbs_g,
        fat_g=result.fat_g,
        same_day_overlap=result.same_day_overlap,
    )


@router.get("/effective", response_model=EffectiveTargetResponse | None)
def get_effective(
    session: DbSession,
    date: Annotated[date_type, Query(description="ISO date (YYYY-MM-DD)")],
) -> EffectiveTargetResponse | None:
    result = get_effective_target(session, day=date)
    if result is None:
        return None
    return EffectiveTargetResponse(
        effective_from=result.effective_from,
        base_calories=result.base_calories,
        protein_g=result.protein_g,
        carbs_g=result.carbs_g,
        fat_g=result.fat_g,
        calories_out=result.calories_out,
        effective_calories=result.effective_calories,
    )
