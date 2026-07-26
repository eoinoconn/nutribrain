"""Tests for T-042: Templates routes.

Covers happy-path and error-path for full CRUD and POST /api/templates/{id}/log.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

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


class TestTemplateRoutes:
    def test_create_template(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/templates",
                    headers=_auth_headers(),
                    json={
                        "name": "Morning Oats",
                        "items": [
                            {
                                "name": "Oats",
                                "quantity": "50",
                                "quantity_unit": "g",
                                "calories": "200",
                                "protein_g": "7",
                                "carbs_g": "35",
                                "fat_g": "4",
                            }
                        ],
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Morning Oats"
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Oats"
        assert data["id"] is not None

    def test_list_templates(self, db_session: Session, make_template, make_template_item) -> None:
        t = make_template(name="Lunch Bowl")
        make_template_item(template_id=t.id, name="Rice", quantity=Decimal("100"))

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get("/api/templates", headers=_auth_headers())
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        names = [t["name"] for t in data]
        assert "Lunch Bowl" in names

    def test_list_templates_with_search(
        self, db_session: Session, make_template, make_template_item
    ) -> None:
        make_template(name="Morning Oats")
        make_template(name="Lunch Bowl")

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.get(
                    "/api/templates", headers=_auth_headers(), params={"q": "oats"}
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Morning Oats"

    def test_patch_template_name(self, db_session: Session, make_template) -> None:
        t = make_template(name="Old Name")

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.patch(
                    f"/api/templates/{t.id}",
                    headers=_auth_headers(),
                    json={"name": "New Name"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_delete_template(self, db_session: Session, make_template) -> None:
        t = make_template(name="To Delete")

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.delete(
                    f"/api/templates/{t.id}",
                    headers=_auth_headers(),
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["deleted"] is True

    def test_log_template(
        self, db_session: Session, make_food, make_template, make_template_item
    ) -> None:
        food = make_food(name="Chicken Breast")
        t = make_template(name="Dinner")
        make_template_item(
            template_id=t.id, name="Chicken Breast", food_id=food.id, quantity=Decimal("150")
        )

        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    f"/api/templates/{t.id}/log",
                    headers=_auth_headers(),
                    json={
                        "logged_at": "2026-07-26T12:00:00Z",
                        "local_tz": "Europe/Dublin",
                        "quantity_scale": "1.5",
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["meal_type"] is not None
        assert len(data["items"]) == 1
        # quantity should be scaled: 150 * 1.5 = 225
        assert Decimal(str(data["items"][0]["quantity"])) == Decimal("225.0")

    def test_log_template_not_found(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.post(
                    "/api/templates/99999/log",
                    headers=_auth_headers(),
                    json={
                        "logged_at": "2026-07-26T12:00:00Z",
                        "local_tz": "Europe/Dublin",
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert response.json()["error"] == "template_not_found"

    def test_patch_template_not_found(self, db_session: Session) -> None:
        app = create_app(include_mcp_mount=False)
        app.dependency_overrides[get_session] = _override_session(db_session)
        try:
            with TestClient(app) as client:
                response = client.patch(
                    "/api/templates/99999",
                    headers=_auth_headers(),
                    json={"name": "Nope"},
                )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert response.json()["error"] == "template_not_found"
