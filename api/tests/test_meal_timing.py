from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.db import MealType
from app.domain import infer_meal_type, parse_local_date, resolve_meal_type


def _utc_from_local(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    local_tz: str,
) -> datetime:
    local_dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(local_tz))
    return local_dt.astimezone(ZoneInfo("UTC"))


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (3, 59, MealType.snack),
        (4, 0, MealType.breakfast),
        (10, 59, MealType.breakfast),
        (11, 0, MealType.lunch),
        (15, 59, MealType.lunch),
        (16, 0, MealType.dinner),
        (21, 59, MealType.dinner),
        (22, 0, MealType.snack),
    ],
)
def test_infer_meal_type_window_boundaries(
    hour: int,
    minute: int,
    expected: MealType,
) -> None:
    local_tz = "Europe/Dublin"
    logged_at = _utc_from_local(2026, 1, 15, hour, minute, local_tz)

    assert infer_meal_type(logged_at, local_tz) == expected


def test_midnight_thirty_is_snack_and_on_correct_local_date() -> None:
    local_tz = "Europe/Dublin"
    logged_at = _utc_from_local(2026, 2, 2, 0, 30, local_tz)

    assert infer_meal_type(logged_at, local_tz) == MealType.snack
    assert logged_at.astimezone(ZoneInfo(local_tz)).date() == date(2026, 2, 2)


def test_resolve_meal_type_explicit_override_wins() -> None:
    local_tz = "Europe/Dublin"
    logged_at = _utc_from_local(2026, 3, 1, 8, 0, local_tz)

    assert resolve_meal_type(MealType.dinner, logged_at, local_tz) == MealType.dinner


def test_parse_local_date_handles_today_yesterday_and_iso() -> None:
    local_tz = "Europe/Dublin"
    now = datetime(2026, 1, 10, 0, 30, tzinfo=ZoneInfo("UTC"))

    assert parse_local_date("today", local_tz, now=now) == date(2026, 1, 10)
    assert parse_local_date("yesterday", local_tz, now=now) == date(2026, 1, 9)
    assert parse_local_date("2026-05-07", local_tz, now=now) == date(2026, 5, 7)


def test_parse_local_date_is_resolved_in_caller_timezone() -> None:
    now = datetime(2026, 1, 10, 23, 30, tzinfo=ZoneInfo("UTC"))

    assert parse_local_date("today", "Pacific/Auckland", now=now) == date(2026, 1, 11)
    assert parse_local_date("yesterday", "Pacific/Auckland", now=now) == date(2026, 1, 10)


def test_parse_local_date_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="today"):
        parse_local_date("not-a-date", "Europe/Dublin")


def test_infer_meal_type_requires_aware_logged_at() -> None:
    aware_dt = datetime(2026, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
    naive_dt = aware_dt.replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone-aware"):
        infer_meal_type(naive_dt, "Europe/Dublin")
