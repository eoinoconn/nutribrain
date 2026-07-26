"""Optional Sentry integration — no-op when SENTRY_DSN is unset."""

from __future__ import annotations

import sentry_sdk
from sentry_sdk.types import Event, Hint

from app.settings import settings


def _before_send(event: Event, hint: Hint) -> Event | None:
    """Scrub request bodies and authorization headers from events."""

    request = event.get("request")
    if request:
        # Remove request body entirely.
        request.pop("data", None)

        # Strip Authorization header.
        headers = request.get("headers")
        if headers:
            if isinstance(headers, dict):
                headers.pop("Authorization", None)
                headers.pop("authorization", None)
            elif isinstance(headers, list):
                request["headers"] = [(k, v) for k, v in headers if k.lower() != "authorization"]

    return event


def init_sentry() -> None:
    """Initialize Sentry if a DSN is configured; otherwise do nothing."""

    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        send_default_pii=False,
        before_send=_before_send,
    )
