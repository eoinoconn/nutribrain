"""Auth, health, and CORS tests (T-030).

Proves G7 (``docs/decisions.md``): a request to ``/mcp`` with no
``Authorization`` header must be rejected. It only is because auth is
enforced by ``AuthMiddleware`` wrapping the whole ASGI stack, not by a
``Depends(require_auth)`` on a FastAPI router — a router dependency does not
run for a mounted ASGI sub-application like the FastMCP app.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _mcp_headers(authorization: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json, text/event-stream"}
    if authorization is not None:
        headers["Authorization"] = authorization
    return headers


class TestApiAuth:
    def test_missing_token_rejected(self, client: TestClient) -> None:
        response = client.get("/api/anything")
        assert response.status_code == 401

    def test_wrong_token_rejected(self, client: TestClient) -> None:
        response = client.get("/api/anything", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_malformed_header_rejected(self, client: TestClient) -> None:
        response = client.get("/api/anything", headers={"Authorization": settings.app_token})
        assert response.status_code == 401

    def test_correct_token_passes_auth(self, client: TestClient) -> None:
        response = client.get(
            "/api/anything", headers={"Authorization": f"Bearer {settings.app_token}"}
        )
        # No /api routes exist yet (T-040+), so a valid token still 404s —
        # the point is it isn't rejected for auth reasons (401).
        assert response.status_code == 404


class TestMcpAuth:
    def test_missing_token_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=_mcp_headers(None),
        )
        assert response.status_code == 401

    def test_wrong_token_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=_mcp_headers("Bearer wrong"),
        )
        assert response.status_code == 401

    def test_malformed_header_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=_mcp_headers(settings.app_token),
        )
        assert response.status_code == 401

    def test_correct_token_passes_auth(self, client: TestClient) -> None:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=_mcp_headers(f"Bearer {settings.app_token}"),
        )
        # Auth passes; the request reaches the MCP session layer instead of
        # being rejected with 401.
        assert response.status_code != 401


def test_health_requires_no_auth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
