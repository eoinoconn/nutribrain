"""Tests for T-045 / EC-07: sync routes.

Covers:
- POST /api/sync/intervals: syncs today's planned_workouts, returns
  days_synced (workouts upserted)/failures
- POST /api/sync/intervals: upstream failure maps to 503 intervals_unavailable
- GET /api/sync/status: reflects the last sync outcome
- PUT /api/sync/intervals/manual: writes source: manual
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import nullcontext
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import settings as settings_module
from app.api.sync import get_fetch_activities, get_fetch_planned, get_status_session_factory
from app.db import IntervalsCaloriesOut, IntervalsSource, get_session
from app.domain.errors import IntervalsUnavailableError
from app.domain.meal_timing import parse_local_date
from app.intervals.client import ActivityDetail, PlannedEventDetail
from app.main import create_app

# Matches the route's own "today" resolution (local tz, not UTC) — using
# UTC here instead would flake near a UTC/local-tz day boundary (a local tz
# ahead of UTC rolls its date over before UTC does).
_TODAY = parse_local_date("today", local_tz=settings_module.settings.tz)


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_module.settings.app_token}"}


def _override_session(db_session: Session):
    def _dependency() -> Iterator[Session]:
        yield db_session

    return _dependency


def _client_with_overrides(db_session: Session, *, fetch_activities=None, fetch_planned=None):
    app = create_app(include_mcp_mount=False)
    app.dependency_overrides[get_session] = _override_session(db_session)
    app.dependency_overrides[get_fetch_activities] = lambda: (
        fetch_activities or (lambda *, oldest, newest: [])
    )
    app.dependency_overrides[get_fetch_planned] = lambda: (
        fetch_planned or (lambda *, oldest, newest: [])
    )
    app.dependency_overrides[get_status_session_factory] = lambda: lambda: nullcontext(db_session)
    return app


class TestSyncIntervalsRoute:
    def test_sync_today_returns_days_synced(self, db_session: Session) -> None:
        today = _TODAY

        def fetch_activities(*, oldest: date, newest: date) -> list[ActivityDetail]:
            return [
                ActivityDetail(
                    external_id="a1",
                    start_date_local=f"{today.isoformat()}T06:00:00",
                    duration_minutes=45.0,
                    sport_type="Ride",
                    calories=350,
                )
            ]

        app = _client_with_overrides(db_session, fetch_activities=fetch_activities)
        try:
            with TestClient(app) as client:
                response = client.post("/api/sync/intervals", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["from_date"] == today.isoformat()
        assert payload["to_date"] == today.isoformat()
        assert payload["days_synced"] == 1
        assert payload["failures"] == []

    def test_upstream_failure_returns_503(self, db_session: Session) -> None:
        def fetch_planned(*, oldest: date, newest: date) -> list[PlannedEventDetail]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        app = _client_with_overrides(db_session, fetch_planned=fetch_planned)
        try:
            with TestClient(app) as client:
                response = client.post("/api/sync/intervals", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 503
        payload = response.json()
        assert payload["error"] == "intervals_unavailable"


class TestSyncStatusRoute:
    def test_status_before_any_sync(self, db_session: Session) -> None:
        app = _client_with_overrides(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/sync/status", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["last_synced_at"] is None
        assert payload["last_error"] is None

    def test_status_reflects_last_sync(self, db_session: Session) -> None:
        app = _client_with_overrides(db_session)
        try:
            with TestClient(app) as client:
                client.post("/api/sync/intervals", headers=_auth_headers())
                response = client.get("/api/sync/status", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["last_synced_at"] is not None
        assert payload["last_error"] is None


class TestManualCaloriesOutRoute:
    def test_put_manual_override_writes_source_manual(self, db_session: Session) -> None:
        app = _client_with_overrides(db_session)
        try:
            with TestClient(app) as client:
                response = client.put(
                    "/api/sync/intervals/manual",
                    headers=_auth_headers(),
                    json={"date": "2026-07-23", "calories_out": 600},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["date"] == "2026-07-23"
        assert payload["calories_out"] == 600

        row = db_session.scalar(
            select(IntervalsCaloriesOut).where(IntervalsCaloriesOut.date == date(2026, 7, 23))
        )
        assert row is not None
        assert row.source == IntervalsSource.manual
