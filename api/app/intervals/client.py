"""intervals.icu API client (T-060).

Fetches activities for a date range using HTTP Basic auth and returns per-day
calories-out by summing activity-level calories.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.domain.errors import IntervalsUnavailableError
from app.settings import settings

_INTERVALS_ACTIVITIES_URL = "https://intervals.icu/api/v1/athlete/{athlete_id}/activities"
_INTERVALS_BASIC_AUTH_USERNAME = "API_KEY"
_INTERVALS_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=5.0)
_INTERVALS_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def fetch_activity_calories_by_day(
    *,
    oldest: date,
    newest: date,
    athlete_id: str | None = None,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> dict[date, int | None]:
    """Fetch intervals activities and sum per-day calories.

    Returns only days present in the upstream response. For each day, calories
    are computed as the sum of activity ``calories`` fields from that local day.
    If a day has activities but none expose calories, that day maps to ``None``.

    Raises:
        IntervalsUnavailableError: When the upstream call fails after bounded
        retries or returns malformed data.
    """

    if newest < oldest:
        raise ValueError("newest must be on or after oldest")

    resolved_athlete_id = athlete_id or settings.intervals_athlete_id
    resolved_api_key = api_key or settings.intervals_api_key
    url = _INTERVALS_ACTIVITIES_URL.format(athlete_id=resolved_athlete_id)
    params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}
    auth = (_INTERVALS_BASIC_AUTH_USERNAME, resolved_api_key)

    managed_client = client is None
    http_client = client or httpx.Client()

    try:
        for attempt in range(1, _INTERVALS_MAX_ATTEMPTS + 1):
            try:
                response = http_client.get(
                    url,
                    params=params,
                    auth=auth,
                    timeout=_INTERVALS_TIMEOUT,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < _INTERVALS_MAX_ATTEMPTS:
                    continue
                raise IntervalsUnavailableError("intervals.icu sync failed.") from exc

            if (
                response.status_code in _RETRYABLE_STATUS_CODES
                and attempt < _INTERVALS_MAX_ATTEMPTS
            ):
                continue

            if response.is_error:
                raise IntervalsUnavailableError(
                    f"intervals.icu sync failed with status {response.status_code}."
                )

            return _parse_activities_payload(response.json(), oldest=oldest, newest=newest)

        raise IntervalsUnavailableError("intervals.icu sync failed.")
    except (ValueError, TypeError) as exc:
        raise IntervalsUnavailableError(
            "intervals.icu sync failed due to invalid response."
        ) from exc
    finally:
        if managed_client:
            http_client.close()


def _parse_activities_payload(
    payload: Any,
    *,
    oldest: date,
    newest: date,
) -> dict[date, int | None]:
    """Parse activities JSON payload into ``{date: calories_or_none}`` mapping."""

    if not isinstance(payload, list):
        raise ValueError("activities payload must be a list")

    per_day_totals: dict[date, int] = {}
    per_day_has_numeric_calories: dict[date, bool] = {}

    for activity in payload:
        if not isinstance(activity, dict):
            raise ValueError("activity row must be an object")

        activity_day = _extract_activity_day(activity)
        if activity_day < oldest or activity_day > newest:
            continue

        calories = _extract_activity_calories(activity)
        if activity_day not in per_day_totals:
            per_day_totals[activity_day] = 0
            per_day_has_numeric_calories[activity_day] = False

        if calories is not None:
            per_day_totals[activity_day] += calories
            per_day_has_numeric_calories[activity_day] = True

    per_day: dict[date, int | None] = {}
    for day, total in per_day_totals.items():
        if per_day_has_numeric_calories.get(day, False):
            per_day[day] = total
        else:
            per_day[day] = None

    return per_day


def _extract_activity_day(activity: dict[str, Any]) -> date:
    """Extract local activity day from intervals activity timestamp fields."""

    day_like = _first_present(activity, "start_date_local", "start_date", "date")
    if not isinstance(day_like, str):
        raise ValueError("activity row is missing start date")
    # Accept full timestamps and date-only values.
    return date.fromisoformat(day_like[:10])


def _extract_activity_calories(activity: dict[str, Any]) -> int | None:
    """Extract and normalize one activity's calorie value."""

    return _coerce_calories(_first_present(activity, "calories", "Calories", "kcal"))


def _coerce_calories(value: Any) -> int | None:
    """Coerce a calories value to int while preserving null as None."""

    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("calories must not be boolean")
    return int(value)


def _first_present(data: dict[str, Any], *keys: str) -> Any:
    """Return the first key present in data, even when its value is falsy."""

    for key in keys:
        if key in data:
            return data[key]
    return None
