"""Sync routes (T-045, §8): trigger a dashboard sync, read status, manual override."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session, session_scope
from app.domain import get_sync_status, parse_local_date, set_manual_calories_out, sync_intervals
from app.domain.intervals_sync import FetchCaloriesByDay, StatusSessionFactory
from app.intervals.client import fetch_activity_calories_by_day
from app.settings import settings

router = APIRouter(prefix="/api/sync", tags=["sync"])
DbSession = Annotated[Session, Depends(get_session)]


def get_intervals_fetch() -> FetchCaloriesByDay:
    return fetch_activity_calories_by_day


def get_status_session_factory() -> StatusSessionFactory:
    return session_scope


FetchDep = Annotated[FetchCaloriesByDay, Depends(get_intervals_fetch)]
StatusFactoryDep = Annotated[StatusSessionFactory, Depends(get_status_session_factory)]


# --- Response schemas -------------------------------------------------------


class SyncIntervalsResponse(BaseModel):
    from_date: date_type
    to_date: date_type
    days_synced: int
    failures: list[dict[str, object]]


class SyncStatusResponse(BaseModel):
    last_synced_at: datetime | None
    last_error: str | None


class SetManualCaloriesOutRequest(BaseModel):
    date: date_type
    calories_out: int = Field(ge=0)


class ManualCaloriesOutResponse(BaseModel):
    date: date_type
    calories_out: int
    fetched_at: datetime


# --- Routes ------------------------------------------------------------------


@router.post("/intervals", response_model=SyncIntervalsResponse)
def sync_intervals_route(
    session: DbSession,
    fetch: FetchDep,
    status_session_factory: StatusFactoryDep,
) -> SyncIntervalsResponse:
    """Sync today's calories-out (§8 "Dashboard button")."""

    today = parse_local_date("today", local_tz=settings.tz)
    result = sync_intervals(
        session,
        from_date=today,
        to_date=today,
        fetch=fetch,
        status_session_factory=status_session_factory,
    )
    return SyncIntervalsResponse(
        from_date=result.from_date,
        to_date=result.to_date,
        days_synced=result.days_synced,
        failures=result.failures,
    )


@router.get("/status", response_model=SyncStatusResponse)
def sync_status_route(session: DbSession) -> SyncStatusResponse:
    status = get_sync_status(session)
    return SyncStatusResponse(last_synced_at=status.last_synced_at, last_error=status.last_error)


@router.put("/intervals/manual", response_model=ManualCaloriesOutResponse)
def set_manual_calories_out_route(
    payload: SetManualCaloriesOutRequest,
    session: DbSession,
) -> ManualCaloriesOutResponse:
    """Manual calories-out override for a day (§8 "Manual override", G5)."""

    result = set_manual_calories_out(session, day=payload.date, calories_out=payload.calories_out)
    return ManualCaloriesOutResponse(
        date=result.date,
        calories_out=result.calories_out,
        fetched_at=result.fetched_at,
    )
