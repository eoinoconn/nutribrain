from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import settings as settings_module
from app.db import MealType, get_session
from app.main import create_app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_module.settings.app_token}"}


def _override_session(db_session: Session):
    def _dependency() -> Iterator[Session]:
        yield db_session

    return _dependency


class TestDayRoute:
    def test_get_day_returns_grouped_meals(
        self, db_session: Session, make_food, make_meal, make_meal_item, make_target
    ) -> None:
        food = make_food(name="Rice", calories=Decimal("130"), serving_size=Decimal("100"))
        make_target(effective_from=date(2026, 1, 1))
        meal = make_meal(
            logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 20),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("200"), name="Rice")

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/day/2026-07-20", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["date"] == "2026-07-20"
        assert "lunch" in payload["meals"]
        assert len(payload["meals"]["lunch"]) == 1
        assert Decimal(payload["day_totals"]["calories"]) == Decimal("260")
        assert payload["effective_target"] is not None
        assert payload["delta_vs_target"] is not None

    def test_get_day_empty_returns_zero_totals(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/day/2026-07-20", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["date"] == "2026-07-20"
        assert payload["meals"] == {}
        assert Decimal(payload["day_totals"]["calories"]) == Decimal("0")

    def test_get_day_invalid_date_returns_422(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/day/not-a-date", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422


class TestRangeRoute:
    def test_get_range_daily(
        self, db_session: Session, make_food, make_meal, make_meal_item, make_target
    ) -> None:
        food = make_food(name="Rice", calories=Decimal("100"), serving_size=Decimal("100"))
        make_target(effective_from=date(2026, 1, 1))
        meal = make_meal(
            logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 20),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("100"), name="Rice")

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/api/range",
                    params={"from": "2026-07-20", "to": "2026-07-21", "granularity": "day"},
                    headers=_auth_headers(),
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["from_date"] == "2026-07-20"
        assert payload["to_date"] == "2026-07-21"
        assert payload["granularity"] == "day"
        assert len(payload["periods"]) == 2
        # First day has data
        assert Decimal(payload["periods"][0]["totals"]["calories"]) == Decimal("100")
        # Second day is empty
        assert Decimal(payload["periods"][1]["totals"]["calories"]) == Decimal("0")

    def test_get_range_invalid_granularity_returns_422(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/api/range",
                    params={"from": "2026-07-20", "to": "2026-07-21", "granularity": "month"},
                    headers=_auth_headers(),
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_get_range_from_after_to_returns_422(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/api/range",
                    params={"from": "2026-07-22", "to": "2026-07-20"},
                    headers=_auth_headers(),
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_get_range_twelve_months_single_call(self, db_session: Session) -> None:
        """Calendar heatmap needs exactly one call for twelve months."""
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/api/range",
                    params={"from": "2025-07-26", "to": "2026-07-25", "granularity": "day"},
                    headers=_auth_headers(),
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        # 365 days in range (inclusive both ends)
        assert len(payload["periods"]) == 365
