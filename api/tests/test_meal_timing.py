from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.db import MealType
from app.domain import infer_meal_type, localize_naive_datetime, parse_local_date, resolve_meal_type


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


def test_localize_naive_datetime_attaches_local_tz() -> None:
    naive_dt = datetime(2026, 1, 15, 20, 0)  # noqa: DTZ001

    localized = localize_naive_datetime(naive_dt, "Europe/Dublin")

    assert localized.tzinfo is not None
    assert localized.replace(tzinfo=None) == naive_dt
    # Winter: Europe/Dublin is UTC+0.
    assert localized.utcoffset() == timedelta(hours=0)
    assert localized.astimezone(UTC) == datetime(2026, 1, 15, 20, 0, tzinfo=UTC)


def test_localize_naive_datetime_passes_aware_value_through_unchanged() -> None:
    aware_dt = datetime(2026, 1, 15, 20, 0, tzinfo=ZoneInfo("America/New_York"))

    localized = localize_naive_datetime(aware_dt, "Europe/Dublin")

    assert localized is aware_dt


def test_localize_naive_datetime_crosses_dst_transition() -> None:
    # Europe/Dublin observes DST: standard time (winter) is UTC+0, summer time
    # is UTC+1. The clocks spring forward on 2026-03-29.
    before_dst = localize_naive_datetime(datetime(2026, 3, 1, 12, 0), "Europe/Dublin")  # noqa: DTZ001
    after_dst = localize_naive_datetime(datetime(2026, 4, 1, 12, 0), "Europe/Dublin")  # noqa: DTZ001

    assert before_dst.utcoffset() == timedelta(hours=0)
    assert after_dst.utcoffset() == timedelta(hours=1)
    assert before_dst.astimezone(UTC) == datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    assert after_dst.astimezone(UTC) == datetime(2026, 4, 1, 11, 0, tzinfo=UTC)


def test_localize_naive_datetime_does_not_crash_on_dst_gap_or_fold() -> None:
    # 2026-03-29 01:30 local does not exist (spring-forward gap).
    gap = localize_naive_datetime(datetime(2026, 3, 29, 1, 30), "Europe/Dublin")  # noqa: DTZ001
    # 2026-10-25 01:30 local occurs twice (fall-back fold); default fold=0
    # resolves to the first (earlier, pre-transition) occurrence.
    fold = localize_naive_datetime(datetime(2026, 10, 25, 1, 30), "Europe/Dublin")  # noqa: DTZ001

    assert gap.tzinfo is not None
    assert fold.tzinfo is not None
    assert fold.fold == 0
