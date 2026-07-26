from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import settings as settings_module
from app.db import QuantityUnit, get_session
from app.main import create_app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_module.settings.app_token}"}


def _override_session(db_session: Session):
    def _dependency() -> Iterator[Session]:
        yield db_session

    return _dependency


class TestMealRoutes:
    def test_post_meal_creates_meal_with_ad_hoc_item(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/meals",
                    headers=_auth_headers(),
                    json={
                        "items": [
                            {
                                "name": "Quick Snack",
                                "quantity": "50",
                                "quantity_unit": QuantityUnit.g.value,
                                "calories": "200",
                                "protein_g": "10",
                                "carbs_g": "20",
                                "fat_g": "8",
                            }
                        ],
                        "logged_at": "2026-07-26T12:00:00Z",
                        "local_tz": "Europe/Dublin",
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        payload = response.json()
        assert payload["meal_type"] == "lunch"
        assert payload["local_date"] == "2026-07-26"
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["name"] == "Quick Snack"
        assert Decimal(str(item["macros"]["calories"])) == Decimal("200")

    def test_post_meal_food_not_found_returns_readable_error(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/meals",
                    headers=_auth_headers(),
                    json={
                        "items": [
                            {
                                "name": "Nonexistent Food",
                                "quantity": "100",
                                "quantity_unit": QuantityUnit.g.value,
                                "food_id": 999999,
                            }
                        ],
                        "logged_at": "2026-07-26T12:00:00Z",
                        "local_tz": "Europe/Dublin",
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        payload = response.json()
        assert payload["error"] == "food_not_found"
        assert "message" in payload

    def test_delete_meal_removes_meal(self, db_session: Session, make_meal) -> None:
        meal = make_meal()

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.delete(f"/api/meals/{meal.id}", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"deleted": True}

    def test_delete_meal_not_found_returns_readable_error(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.delete("/api/meals/999999", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        payload = response.json()
        assert payload["error"] == "meal_not_found"
        assert "message" in payload

    def test_delete_meal_item_removes_item(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        meal = make_meal()
        item = make_meal_item(meal_id=meal.id)

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.delete(f"/api/meal-items/{item.id}", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"deleted": True}

    def test_delete_meal_item_not_found_returns_readable_error(
        self,
        db_session: Session,
    ) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.delete("/api/meal-items/999999", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        payload = response.json()
        assert payload["error"] == "meal_item_not_found"
        assert "message" in payload
