from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import ServingUnit, get_session
from app.domain import add_food, delete_food, search_foods, set_favorite_food, update_food

router = APIRouter(prefix="/api/foods", tags=["foods"])
DbSession = Annotated[Session, Depends(get_session)]


class FoodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    serving_size: Decimal
    serving_unit: ServingUnit
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sat_fat_g: Decimal | None
    sodium_mg: Decimal | None
    density_g_per_ml: Decimal | None
    is_favorite: bool
    created_at: datetime


class FoodSearchResponse(FoodResponse):
    last_logged_at: datetime | None
    logged_count: int


class CreateFoodRequest(BaseModel):
    name: str = Field(min_length=1)
    serving_size: Decimal
    serving_unit: ServingUnit
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None
    density_g_per_ml: Decimal | None = None
    force: bool = False


class UpdateFoodRequest(BaseModel):
    name: str | None = None
    serving_size: Decimal | None = None
    serving_unit: ServingUnit | None = None
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    fiber_g: Decimal | None = None
    sat_fat_g: Decimal | None = None
    sodium_mg: Decimal | None = None
    density_g_per_ml: Decimal | None = None


class UpdateFoodResponse(BaseModel):
    food: FoodResponse
    recompute_count: int


class FavoriteFoodRequest(BaseModel):
    is_favorite: bool


class DeleteFoodResponse(BaseModel):
    deleted: bool


@router.get("", response_model=list[FoodSearchResponse])
def list_foods(
    session: DbSession,
    q: Annotated[str, Query(description="Fuzzy food query")] = "",
) -> list[FoodSearchResponse]:
    results = search_foods(session, query=q)
    return [
        FoodSearchResponse(
            **FoodResponse.model_validate(result.food).model_dump(),
            last_logged_at=result.last_logged_at,
            logged_count=result.logged_count,
        )
        for result in results
    ]


@router.post("", response_model=FoodResponse, status_code=status.HTTP_201_CREATED)
def create_food(
    payload: CreateFoodRequest,
    session: DbSession,
) -> FoodResponse:
    result = add_food(session, **payload.model_dump())
    return FoodResponse.model_validate(result.food)


@router.patch("/{food_id}", response_model=UpdateFoodResponse)
def patch_food(
    payload: UpdateFoodRequest,
    food_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> UpdateFoodResponse:
    result = update_food(
        session,
        food_id=food_id,
        **payload.model_dump(exclude_unset=True),
    )
    return UpdateFoodResponse(
        food=FoodResponse.model_validate(result.food),
        recompute_count=result.affected_meals_count,
    )


@router.post("/{food_id}/favorite", response_model=FoodResponse)
def favorite_food(
    payload: FavoriteFoodRequest,
    food_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> FoodResponse:
    food = set_favorite_food(session, food_id=food_id, is_favorite=payload.is_favorite)
    return FoodResponse.model_validate(food)


@router.delete("/{food_id}", response_model=DeleteFoodResponse)
def remove_food(
    food_id: Annotated[int, Path(ge=1)],
    session: DbSession,
) -> DeleteFoodResponse:
    delete_food(session, food_id=food_id)
    return DeleteFoodResponse(deleted=True)
