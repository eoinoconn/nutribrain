from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import settings as settings_module
from app.db import ServingUnit, get_session
from app.main import create_app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_module.settings.app_token}"}


def _as_decimal(payload: dict[str, object], key: str) -> Decimal:
    return Decimal(str(payload[key]))


def _override_session(db_session: Session):
    def _dependency() -> Iterator[Session]:
        yield db_session

    return _dependency


class TestFoodRoutes:
    def test_get_foods_search_returns_usage_stats(
        self,
        db_session: Session,
        make_food,
        make_meal,
        make_meal_item,
    ) -> None:
        oats = make_food(name="Overnight Oats", is_favorite=True)
        make_food(name="Chicken Breast")

        meal = make_meal(logged_at=datetime(2026, 7, 20, 8, 30, tzinfo=UTC))
        make_meal_item(meal_id=meal.id, food=oats, quantity=Decimal("50"))

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/foods?q=oat", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["name"] == "Overnight Oats"
        assert payload[0]["is_favorite"] is True
        assert payload[0]["logged_count"] == 1
        assert payload[0]["last_logged_at"].startswith("2026-07-20T08:30:00")

    def test_post_food_creates_food(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/foods",
                    headers=_auth_headers(),
                    json={
                        "name": "Greek Yogurt",
                        "serving_size": "170",
                        "serving_unit": ServingUnit.g.value,
                        "calories": "130",
                        "protein_g": "17",
                        "carbs_g": "6",
                        "fat_g": "4",
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        payload = response.json()
        assert payload["name"] == "Greek Yogurt"
        assert _as_decimal(payload, "calories") == Decimal("130")

    def test_post_food_duplicate_returns_domain_error(self, db_session: Session, make_food) -> None:
        make_food(name="Greek Yogurt")

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/foods",
                    headers=_auth_headers(),
                    json={
                        "name": "Greek Yogurt",
                        "serving_size": "170",
                        "serving_unit": ServingUnit.g.value,
                        "calories": "130",
                        "protein_g": "17",
                        "carbs_g": "6",
                        "fat_g": "4",
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 409
        assert response.json()["error"] == "food_duplicate"

    def test_patch_food_returns_recompute_count(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        food = make_food(name="Rice", calories=Decimal("130"))
        meal = make_meal()
        make_meal_item(meal_id=meal.id, food=food)

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.patch(
                    f"/api/foods/{food.id}",
                    headers=_auth_headers(),
                    json={"calories": "140"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        payload = response.json()
        assert payload["recompute_count"] == 1
        assert _as_decimal(payload["food"], "calories") == Decimal("140")

    def test_patch_food_serving_unit_immutable_error(self, db_session: Session, make_food) -> None:
        food = make_food(serving_unit=ServingUnit.g)

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.patch(
                    f"/api/foods/{food.id}",
                    headers=_auth_headers(),
                    json={"serving_unit": ServingUnit.ml.value},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422
        assert response.json()["error"] == "serving_unit_immutable"

    def test_post_favorite_updates_flag(self, db_session: Session, make_food) -> None:
        food = make_food(is_favorite=False)

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    f"/api/foods/{food.id}/favorite",
                    headers=_auth_headers(),
                    json={"is_favorite": True},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["is_favorite"] is True

    def test_post_favorite_not_found_returns_domain_error(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/foods/999999/favorite",
                    headers=_auth_headers(),
                    json={"is_favorite": True},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert response.json()["error"] == "food_not_found"

    def test_delete_food_soft_deletes(self, db_session: Session, make_food) -> None:
        food = make_food()

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.delete(f"/api/foods/{food.id}", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"deleted": True}

    def test_delete_food_not_found_returns_domain_error(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.delete("/api/foods/999999", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert response.json()["error"] == "food_not_found"
