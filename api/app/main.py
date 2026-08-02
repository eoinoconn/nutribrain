from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider

from app import settings as settings_module
from app.api.day import router as day_router
from app.api.foods import router as foods_router
from app.api.meals import router as meals_router
from app.api.planned_workouts import router as planned_workouts_router
from app.api.settings import router as settings_router
from app.api.sync import router as sync_router
from app.api.targets import router as targets_router
from app.api.templates import router as templates_router
from app.auth import AuthMiddleware
from app.db import engine
from app.domain.errors import DomainError
from app.logging import configure_logging
from app.mcp import register_all_tools
from app.mcp_auth import PostgresKeyValueStore, SingleEmailTokenVerifier
from app.middleware import RequestLoggingMiddleware
from app.sentry import init_sentry

# Configure structured logging on import (before any logger is used)
configure_logging(settings_module.settings.log_level)

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
    "invalid_timezone": 422,
    "naive_datetime": 422,
}


def _validate_startup_settings() -> None:
    """Fail fast if any required runtime setting is missing or blank."""

    required_values = {
        "database_url": settings_module.settings.database_url,
        "app_token": settings_module.settings.app_token,
        "cors_origin": settings_module.settings.cors_origin,
    }
    blank = [name for name, value in required_values.items() if not value or not value.strip()]
    if blank:
        fields = ", ".join(sorted(blank))
        raise RuntimeError(
            f"Invalid environment configuration: blank required setting(s): {fields}"
        )

    # MCP OAuth (docs/features/mcp_oauth.md, F-103) is opt-in: an operator who
    # hasn't set any of these four yet just hasn't gotten to this feature, and
    # `/mcp` keeps working exactly as before (static bearer token only — see
    # `_build_mcp_auth_provider`). But *some* set and others missing means the
    # feature was half-configured, which would either leave `/mcp` OAuth
    # half-wired or silently fall back to the static-token-only behavior while
    # an operator believes OAuth is live — fail loudly instead.
    oauth_values = {
        "google_oauth_client_id": settings_module.settings.google_oauth_client_id,
        "google_oauth_client_secret": settings_module.settings.google_oauth_client_secret,
        "mcp_allowed_email": settings_module.settings.mcp_allowed_email,
        "mcp_public_base_url": settings_module.settings.mcp_public_base_url,
    }
    oauth_blank = [name for name, value in oauth_values.items() if not value or not value.strip()]
    if oauth_blank and len(oauth_blank) != len(oauth_values):
        fields = ", ".join(sorted(oauth_blank))
        raise RuntimeError(
            "Invalid environment configuration: MCP OAuth is partially configured "
            f"(some of google_oauth_client_id/google_oauth_client_secret/"
            f"mcp_allowed_email/mcp_public_base_url are set, others aren't); "
            f"missing: {fields}"
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Compose startup/shutdown for both FastAPI and mounted FastMCP apps."""

    _validate_startup_settings()
    init_sentry()
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


async def _handle_domain_error(_request: Request, exc: Exception) -> Response:
    domain_exc = cast(DomainError, exc)
    return JSONResponse(
        status_code=_status_for_domain_error(domain_exc.error),
        content=jsonable_encoder(_domain_error_payload(domain_exc)),
    )


def _build_mcp_auth_provider() -> GoogleProvider | None:
    """Build the `/mcp` OAuth provider (F-103), or `None` if OAuth isn't configured.

    Returns `None` when any of the four MCP OAuth settings is unset — this is
    the common case for local dev and most test environments, which have no
    Google OAuth app configured — so `FastMCP("nutribrain", auth=None)` behaves
    identically to today's `FastMCP("nutribrain")` (see `fastmcp.server.server`,
    `auth` defaults to `None`). `_validate_startup_settings` above guarantees
    that if we get past it with any of the four set, all four are set, so this
    function doesn't need to re-validate partial configuration.

    When configured, this constructs FastMCP's `GoogleProvider` (the OAuth
    proxy in front of Google, per `docs/features/mcp_oauth.md`) and then
    reaches into its private `_token_validator` attribute to wrap it with
    `SingleEmailTokenVerifier` (F-102).

    Why the private-attribute reach-around: `GoogleProvider.__init__`
    (`fastmcp/server/auth/providers/google.py`) builds its own
    `GoogleTokenVerifier` internally and passes it straight to
    `OAuthProxy.__init__(token_verifier=...)`
    (`fastmcp/server/auth/oauth_proxy/proxy.py`), which stores it as
    `self._token_validator` (assigned once, around line 612 in the installed
    version at the time this was written) and calls
    `self._token_validator.verify_token(...)` at every verification call site.
    There is no constructor parameter on `GoogleProvider` or `OAuthProxy` to
    inject a wrapped/custom verifier — this was confirmed by reading the
    installed `fastmcp` source, not assumed. Swapping the attribute after
    construction is the only seam available, so it's done deliberately here,
    not as an oversight: if `fastmcp` is upgraded and this private attribute
    is renamed or removed, this reach-around silently stops enforcing the
    single-email allow-list (any Google account would then authenticate).
    `tests/test_mcp_auth_wiring.py` guards against that by asserting, against
    the real `GoogleProvider`, that `_token_validator` is in fact a
    `SingleEmailTokenVerifier` and that it actually gates `verify_token` — so
    an upgrade that breaks this silently fails that test instead of silently
    degrading auth. Re-check this reach-around whenever `fastmcp` is upgraded.
    """

    s = settings_module.settings
    if not (
        s.google_oauth_client_id
        and s.google_oauth_client_secret
        and s.mcp_allowed_email
        and s.mcp_public_base_url
    ):
        return None

    provider = GoogleProvider(
        client_id=s.google_oauth_client_id,
        client_secret=s.google_oauth_client_secret,
        base_url=s.mcp_public_base_url,
        client_storage=PostgresKeyValueStore(),
        # "email" is required, not optional: Google only includes
        # email/email_verified in the tokeninfo/userinfo response when that
        # scope was actually granted — "openid" alone gets you `sub` only.
        # SingleEmailTokenVerifier (F-102) depends on both claims being
        # present, so without this scope every login is rejected with
        # "email_not_verified" regardless of which account signs in
        # (reproduced live — see docs/features/mcp_oauth.md).
        required_scopes=["openid", "email"],
    )
    provider._token_validator = SingleEmailTokenVerifier(
        provider._token_validator, s.mcp_allowed_email
    )
    return provider


mcp = FastMCP("nutribrain", auth=_build_mcp_auth_provider())
register_all_tools(mcp)
mcp_app = mcp.http_app(path="/mcp")


def create_app(*, include_mcp_mount: bool = True) -> FastAPI:
    app = FastAPI(title="nutribrain", lifespan=_lifespan)

    # Middleware order (last added = outermost in ASGI):
    # 1. AuthMiddleware — rejects unauthenticated requests
    # 2. CORSMiddleware — handles preflight before auth sees OPTIONS
    # 3. RequestLoggingMiddleware — outermost; binds request_id, logs slow requests
    app.add_middleware(
        AuthMiddleware,
        token=settings_module.settings.app_token or "",
        oauth_enabled=mcp.auth is not None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings_module.settings.cors_origin or ""],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.add_exception_handler(DomainError, _handle_domain_error)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(foods_router)
    app.include_router(day_router)
    app.include_router(meals_router)
    app.include_router(planned_workouts_router)
    app.include_router(settings_router)
    app.include_router(sync_router)
    app.include_router(targets_router)
    app.include_router(templates_router)

    if include_mcp_mount:
        # Mounted last: Mount("/", ...) matches every path, so routes defined above it
        # (like /health) must be registered first or the mount would shadow them.
        app.mount("/", mcp_app)

    return app


app = create_app()
