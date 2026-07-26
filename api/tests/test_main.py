from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import settings as settings_module
from app.domain.errors import FoodAmbiguousError, ServingUnitImmutableError
from app.main import create_app


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings_module.settings.app_token}"}


def _app_with_domain_error_route(error: Exception) -> FastAPI:
    app = create_app(include_mcp_mount=False)

    @app.get("/api/_raise-domain-error")
    def raise_domain_error() -> None:
        raise error

    return app


def test_domain_error_maps_to_appendix_c_envelope_with_candidates() -> None:
    app = _app_with_domain_error_route(
        FoodAmbiguousError(
            "bagel",
            [
                {"id": 12, "name": "Brennans Bagel", "calories": 260},
                {"id": 13, "name": "M&S Sourdough Bagel", "calories": 240},
            ],
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/_raise-domain-error", headers=_auth_headers())

    assert response.status_code == 409
    assert response.json() == {
        "error": "food_ambiguous",
        "message": "Multiple foods match 'bagel'. Specify one.",
        "candidates": [
            {"id": 12, "name": "Brennans Bagel", "calories": 260},
            {"id": 13, "name": "M&S Sourdough Bagel", "calories": 240},
        ],
    }


def test_domain_error_maps_to_status_without_candidates() -> None:
    app = _app_with_domain_error_route(ServingUnitImmutableError())

    with TestClient(app) as client:
        response = client.get("/api/_raise-domain-error", headers=_auth_headers())

    assert response.status_code == 422
    assert response.json() == {
        "error": "serving_unit_immutable",
        "message": "Cannot change serving_unit. Create a new food instead.",
    }


def test_startup_fails_fast_on_blank_required_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.settings, "app_token", " ")

    with pytest.raises(RuntimeError, match="blank required setting"), TestClient(create_app()):
        pass
