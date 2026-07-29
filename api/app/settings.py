from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    app_token: str | None = None
    cors_origin: str | None = None
    intervals_api_key: str
    intervals_athlete_id: str
    tz: str = "Europe/Dublin"
    intervals_sync_days: int = 3
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    vite_api_base: str | None = None

    # MCP OAuth (docs/features/mcp_oauth.md, F-103). All four are optional at
    # import time — most local dev/test environments have no Google OAuth app
    # configured yet — but `app.main._validate_startup_settings` fails loudly
    # if only some of them are set, since a partial configuration would
    # silently leave `/mcp` either unauthenticated or unreachable.
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    mcp_allowed_email: str | None = None
    # Public base URL FastMCP's GoogleProvider uses to construct the OAuth
    # redirect (`{mcp_public_base_url}/auth/callback` by default) and to
    # advertise endpoints in its metadata. `vite_api_base` is a distinct,
    # web-facing/Vite-only setting (the API base URL baked into the dashboard
    # build) and isn't reused here.
    mcp_public_base_url: str | None = None


try:
    settings = Settings()  # type: ignore[call-arg]
except ValidationError as exc:
    # Fail fast and loudly during import if required env vars are missing.
    raise RuntimeError("Invalid environment configuration") from exc
