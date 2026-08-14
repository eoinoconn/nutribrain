"""Account-level settings routes (§6a, EC-06): thin adapters over app/domain/settings.py."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain import get_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])
DbSession = Annotated[Session, Depends(get_session)]


# --- Request / Response schemas ---------------------------------------------


class AppSettingsResponse(BaseModel):
    local_timezone: str


class UpdateSettingsRequest(BaseModel):
    local_timezone: str


# --- Routes ------------------------------------------------------------------


@router.get("", response_model=AppSettingsResponse)
def get_settings_route(session: DbSession) -> AppSettingsResponse:
    result = get_settings(session)
    return AppSettingsResponse(local_timezone=result.local_timezone)


@router.patch("", response_model=AppSettingsResponse)
def update_settings_route(
    payload: UpdateSettingsRequest,
    session: DbSession,
) -> AppSettingsResponse:
    result = update_settings(session, local_timezone=payload.local_timezone)
    return AppSettingsResponse(local_timezone=result.local_timezone)
