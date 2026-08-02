"""Tests for EC-06: settings routes.

Covers:
- GET /api/settings: returns the singleton's current local_timezone (default UTC)
- PATCH /api/settings: updates and returns the new local_timezone
- Error path: PATCH /api/settings with an invalid timezone returns 422
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


class TestSettingsRoutes:
    def test_get_settings_returns_default_utc(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/settings", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"local_timezone": "UTC"}

    def test_patch_settings_updates_and_returns_new_timezone(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.patch(
                    "/api/settings",
                    headers=_auth_headers(),
                    json={"local_timezone": "America/New_York"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"local_timezone": "America/New_York"}

    def test_patch_settings_invalid_timezone_returns_422(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.patch(
                    "/api/settings",
                    headers=_auth_headers(),
                    json={"local_timezone": "Not/A_Timezone"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422
        payload = response.json()
        assert payload["error"] == "invalid_timezone"
