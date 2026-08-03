"""Planned workout routes (EC-04, §6 "Manual fallback"): thin adapter over
app/domain/planned_workouts.py.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain import create_manual_planned_workout

router = APIRouter(prefix="/api/planned-workouts", tags=["planned-workouts"])
DbSession = Annotated[Session, Depends(get_session)]


# --- Request / Response schemas ---------------------------------------------


class CreatePlannedWorkoutRequest(BaseModel):
    start_at: datetime
    estimated_calories: int = Field(ge=0)
    # Not part of the small "start time + estimated kcal" form (§6); a
    # sensible default is used server-side when omitted (see
    # app/domain/planned_workouts.py's DEFAULT_DURATION_MINUTES).
    duration_minutes: int | None = Field(default=None, ge=1)


class PlannedWorkoutResponse(BaseModel):
    id: int
    source: str
    local_date: date_type
    start_at: datetime
    duration_minutes: int
    estimated_calories: int | None
    status: str


# --- Routes ------------------------------------------------------------------


@router.post("", response_model=PlannedWorkoutResponse, status_code=status.HTTP_201_CREATED)
def create_planned_workout(
    payload: CreatePlannedWorkoutRequest,
    session: DbSession,
) -> PlannedWorkoutResponse:
    result = create_manual_planned_workout(
        session,
        start_at=payload.start_at,
        estimated_calories=payload.estimated_calories,
        duration_minutes=payload.duration_minutes,
    )
    return PlannedWorkoutResponse(
        id=result.id,
        source=str(result.source),
        local_date=result.local_date,
        start_at=result.start_at,
        duration_minutes=result.duration_minutes,
        estimated_calories=result.estimated_calories,
        status=str(result.status),
    )
