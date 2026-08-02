"""Meal-time inference and shared local-date parsing helpers.

These helpers keep local-time and local-date interpretation in the domain layer
so API and MCP adapters apply the same behavior.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.db import MealType


def infer_meal_type(logged_at: datetime, local_tz: str) -> MealType:
    """Infer meal type from local clock time using spec-defined windows.

    Windows are interpreted in the meal's local timezone:
    - breakfast: 04:00-10:59
    - lunch: 11:00-15:59
    - dinner: 16:00-21:59
    - snack: 22:00-03:59 (and any non-matching edge)
    """

    local_time = _to_local_time(logged_at, local_tz)

    if time(4, 0) <= local_time <= time(10, 59, 59, 999999):
        return MealType.breakfast
    if time(11, 0) <= local_time <= time(15, 59, 59, 999999):
        return MealType.lunch
    if time(16, 0) <= local_time <= time(21, 59, 59, 999999):
        return MealType.dinner
    return MealType.snack


def resolve_meal_type(meal_type: MealType | None, logged_at: datetime, local_tz: str) -> MealType:
    """Return caller-provided meal_type or infer it from local time."""

    if meal_type is not None:
        return meal_type
    return infer_meal_type(logged_at, local_tz)


def parse_local_date(value: str | date, local_tz: str, now: datetime | None = None) -> date:
    """Parse `today`/`yesterday`/ISO date tokens in the caller's local timezone."""

    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("Date must be 'today', 'yesterday', or ISO YYYY-MM-DD")

    token = value.strip().lower()
    local_now = _get_now(now).astimezone(ZoneInfo(local_tz))

    if token == "today":
        return local_now.date()
    if token == "yesterday":
        return (local_now - timedelta(days=1)).date()

    try:
        return date.fromisoformat(token)
    except ValueError as exc:
        raise ValueError("Date must be 'today', 'yesterday', or ISO YYYY-MM-DD") from exc


def localize_naive_datetime(value: datetime, local_tz: str) -> datetime:
    """Interpret a naive datetime in `local_tz`; pass an aware datetime through unchanged.

    A naive `logged_at` (no offset/`Z`) is localized by attaching `local_tz` as
    its tzinfo — the wall-clock value is taken as-is in that zone. An aware
    datetime already carries an explicit offset and is returned unchanged.

    DST edge cases: `zoneinfo` resolves ambiguous times (fall-back) using the
    default `fold=0` (the earlier of the two occurrences) and non-existent
    times (spring-forward gap) by extrapolating the offset that was in effect
    before the gap, per PEP 495. Neither case raises; both are accepted as-is
    without extra disambiguation, which is sufficient for a single-user app.
    """

    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=ZoneInfo(local_tz))


def _to_local_time(logged_at: datetime, local_tz: str) -> time:
    if logged_at.tzinfo is None:
        raise ValueError("logged_at must be timezone-aware")

    local_dt = logged_at.astimezone(ZoneInfo(local_tz))
    return local_dt.timetz().replace(tzinfo=None)


def _get_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now
