"""Tests for T-045: sync routes.

Covers:
- POST /api/sync/intervals: syncs today, returns days_synced/failures
- POST /api/sync/intervals: upstream failure maps to 503 intervals_unavailable
- GET /api/sync/status: reflects the last sync outcome
- PUT /api/sync/intervals/manual: writes source: manual
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import nullcontext
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import settings as settings_module
from app.api.sync import get_intervals_fetch, get_status_session_factory
from app.db import IntervalsCaloriesOut, IntervalsSource, get_session
from app.domain.errors import IntervalsUnavailableError
from app.main import create_app

_TODAY = datetime.now(UTC).date()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_module.settings.app_token}"}


def _override_session(db_session: Session):
    def _dependency() -> Iterator[Session]:
        yield db_session

    return _dependency


def _client_with_overrides(db_session: Session, *, fetch):
    app = create_app(include_mcp_mount=False)
    app.dependency_overrides[get_session] = _override_session(db_session)
    app.dependency_overrides[get_intervals_fetch] = lambda: fetch
    app.dependency_overrides[get_status_session_factory] = lambda: lambda: nullcontext(db_session)
    return app


class TestSyncIntervalsRoute:
    def test_sync_today_returns_days_synced(self, db_session: Session) -> None:
        today = _TODAY

        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {today: 350}

        app = _client_with_overrides(db_session, fetch=fetch)
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
        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            raise IntervalsUnavailableError("intervals.icu sync failed.")

        app = _client_with_overrides(db_session, fetch=fetch)
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
        app = _client_with_overrides(db_session, fetch=lambda **_: {})
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
        today = _TODAY

        def fetch(*, oldest: date, newest: date) -> dict[date, int | None]:
            return {today: 200}

        app = _client_with_overrides(db_session, fetch=fetch)
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
        app = _client_with_overrides(db_session, fetch=lambda **_: {})
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
