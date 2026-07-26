from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    app_token: str
    intervals_api_key: str
    intervals_athlete_id: str
    tz: str = "Europe/Dublin"
    intervals_sync_days: int = 3
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    vite_api_base: str | None = None


try:
    settings = Settings()  # type: ignore[call-arg]
except ValidationError as exc:
    # Fail fast and loudly during import if required env vars are missing.
    raise RuntimeError("Invalid environment configuration") from exc
