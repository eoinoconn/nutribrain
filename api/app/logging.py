"""Structured logging configuration (T-032).

Configures structlog for the application:
- JSON output in production, pretty console in dev (``LOG_LEVEL=DEBUG`` implies dev)
- Level controlled by ``LOG_LEVEL`` environment variable
- A redaction processor that unconditionally strips Authorization header values
- Request-scoped context via structlog context variables
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


def _redact_authorization(
    _logger: object, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Processor that redacts any Authorization header value from log events.

    Implemented as a processor (not a convention) so it cannot be forgotten.
    Checks common key patterns where auth headers might appear.
    """
    for key in list(event_dict.keys()):
        if key.lower() in ("authorization", "auth_header"):
            event_dict[key] = "[REDACTED]"
    # Also redact if authorization appears nested in a headers dict
    if "headers" in event_dict and isinstance(event_dict["headers"], dict):
        headers = event_dict["headers"]
        for k in list(headers.keys()):
            if k.lower() == "authorization":
                headers[k] = "[REDACTED]"
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog and stdlib logging for the application."""

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Dev mode uses pretty console rendering; production uses JSON.
    # DEBUG level implies local development; explicit ENVIRONMENT=dev also triggers it.
    is_dev = log_level.upper() == "DEBUG" or os.getenv("ENVIRONMENT") == "dev"

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_authorization,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_dev:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to route through structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
