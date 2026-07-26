"""Shared date argument parsing for MCP tools.

All date-like tool arguments accept `today`, `yesterday`, or ISO YYYY-MM-DD,
resolved in the caller's local timezone.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.domain import parse_local_date


def resolve_date_arg(
    value: str | date,
    *,
    local_tz: str,
    now: datetime | None = None,
) -> date:
    """Resolve one date argument from token/date input."""

    return parse_local_date(value=value, local_tz=local_tz, now=now)


def resolve_date_range_args(
    *,
    from_value: str | date,
    to_value: str | date,
    local_tz: str,
    now: datetime | None = None,
) -> tuple[date, date]:
    """Resolve and validate an inclusive date range."""

    start = parse_local_date(value=from_value, local_tz=local_tz, now=now)
    end = parse_local_date(value=to_value, local_tz=local_tz, now=now)
    if start > end:
        raise ValueError("from_date must be on or before to_date")
    return start, end


def default_sync_window(*, local_tz: str, now: datetime | None = None) -> tuple[date, date]:
    """Return the default sync window: last 7 days inclusive."""

    local_today = parse_local_date("today", local_tz=local_tz, now=now)
    return local_today - timedelta(days=6), local_today
