"""Tests for T-043: targets routes.

Covers:
- GET /api/targets: returns versioned history ordered by effective_from desc
- POST /api/targets: creates a new target, returns 201
- GET /api/targets/effective?date=: returns effective target for a given date
- Error path: GET /api/targets/effective returns null when no target exists
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

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


class TestTargetRoutes:
    def test_get_targets_returns_versioned_history_desc(
        self, db_session: Session, make_target
    ) -> None:
        make_target(effective_from=date(2026, 1, 1), base_calories=1800)
        make_target(effective_from=date(2026, 6, 1), base_calories=2200)

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/targets", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 2
        # Ordered by effective_from desc
        assert payload[0]["effective_from"] == "2026-06-01"
        assert payload[0]["base_calories"] == 2200
        assert payload[1]["effective_from"] == "2026-01-01"
        assert payload[1]["base_calories"] == 1800

    def test_post_target_creates_and_returns_201(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/targets",
                    headers=_auth_headers(),
                    json={
                        "effective_from": "2026-07-01",
                        "base_calories": 2500,
                        "protein_g": 180,
                        "carbs_g": 260,
                        "fat_g": 85,
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        payload = response.json()
        assert payload["base_calories"] == 2500
        assert payload["protein_g"] == 180
        assert payload["carbs_g"] == 260
        assert payload["fat_g"] == 85
        assert payload["effective_from"] == "2026-07-01"
        assert payload["same_day_overlap"] is False

    def test_post_target_same_day_overlap(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2026, 7, 1), base_calories=2000)

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/targets",
                    headers=_auth_headers(),
                    json={
                        "effective_from": "2026-07-01",
                        "base_calories": 2500,
                        "protein_g": 180,
                        "carbs_g": 260,
                        "fat_g": 85,
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        assert response.json()["same_day_overlap"] is True

    def test_get_effective_returns_target_for_date(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/api/targets/effective?date=2026-07-26", headers=_auth_headers()
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["base_calories"] == 2000
        assert payload["effective_from"] == "2026-01-01"
        assert payload["calories_out"] is None
        assert payload["effective_calories"] == 2000

    def test_get_effective_returns_null_when_no_target(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/api/targets/effective?date=2026-07-26", headers=_auth_headers()
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() is None
