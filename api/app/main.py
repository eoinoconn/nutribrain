from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastmcp import FastMCP

from app import settings as settings_module
from app.api.foods import router as foods_router
from app.api.templates import router as templates_router
from app.auth import AuthMiddleware
from app.db import engine
from app.domain.errors import DomainError

ERROR_STATUS_BY_CODE: dict[str, int] = {
    "unauthorized": 401,
    "food_not_found": 404,
    "food_ambiguous": 409,
    "food_duplicate": 409,
    "serving_unit_immutable": 422,
    "template_not_found": 404,
    "intervals_unavailable": 503,
    "meal_not_found": 404,
    "meal_item_not_found": 404,
}


def _validate_startup_settings() -> None:
    """Fail fast if any required runtime setting is missing or blank."""

    required_values = {
        "database_url": settings_module.settings.database_url,
        "app_token": settings_module.settings.app_token,
        "cors_origin": settings_module.settings.cors_origin,
    }
    blank = [name for name, value in required_values.items() if not value.strip()]
    if blank:
        fields = ", ".join(sorted(blank))
        raise RuntimeError(
            f"Invalid environment configuration: blank required setting(s): {fields}"
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Compose startup/shutdown for both FastAPI and mounted FastMCP apps."""

    _validate_startup_settings()
    # Ensure the process-wide engine is initialized during startup.
    _ = engine
    async with mcp_app.lifespan(app):
        yield
    engine.dispose()


def _status_for_domain_error(error_code: str) -> int:
    return ERROR_STATUS_BY_CODE.get(error_code, 400)


def _domain_error_payload(exc: DomainError) -> dict[str, object]:
    payload: dict[str, object] = {"error": exc.error, "message": exc.message}
    if exc.candidates is not None:
        payload["candidates"] = exc.candidates
    return payload


async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=_status_for_domain_error(exc.error),
        content=jsonable_encoder(_domain_error_payload(exc)),
    )


mcp = FastMCP("nutribrain")
mcp_app = mcp.http_app(path="/mcp")


def create_app(*, include_mcp_mount: bool = True) -> FastAPI:
    app = FastAPI(title="nutribrain", lifespan=_lifespan)

    # Added last so it sits outermost and handles CORS preflight (OPTIONS, sent
    # without an Authorization header) before AuthMiddleware ever sees it.
    app.add_middleware(AuthMiddleware, token=settings_module.settings.app_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings_module.settings.cors_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(DomainError, _handle_domain_error)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(foods_router)
    app.include_router(templates_router)

    if include_mcp_mount:
        # Mounted last: Mount("/", ...) matches every path, so routes defined above it
        # (like /health) must be registered first or the mount would shadow them.
        app.mount("/", mcp_app)

    return app


app = create_app()
