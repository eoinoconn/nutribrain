"""Tests for EC-04: POST /api/planned-workouts route.

Covers:
- happy path: 201 with the created manual row
- error path: naive start_at returns 422 with the naive_datetime error code
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import settings as settings_module
from app.db import get_session
from app.main import create_app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_module.settings.app_token}"}


def _override_session(db_session: Session):
    def _dependency() -> Iterator[Session]:
        yield db_session

    return _dependency


class TestCreatePlannedWorkoutRoute:
    def test_create_manual_planned_workout_returns_201(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/planned-workouts",
                    headers=_auth_headers(),
                    json={"start_at": "2026-08-02T07:00:00+00:00", "estimated_calories": 450},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        body = response.json()
        assert body["source"] == "manual"
        assert body["status"] == "planned"
        assert body["estimated_calories"] == 450
        assert body["local_date"] == "2026-08-02"
        assert body["duration_minutes"] == 60

    def test_naive_start_at_returns_422(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/planned-workouts",
                    headers=_auth_headers(),
                    json={"start_at": "2026-08-02T07:00:00", "estimated_calories": 450},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422
        assert response.json()["error"] == "naive_datetime"
