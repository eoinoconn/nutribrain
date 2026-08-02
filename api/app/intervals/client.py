"""intervals.icu API client (T-060).

Fetches per-activity/per-event detail for a date range using HTTP Basic auth
(``fetch_activities_detailed``, ``fetch_planned_events``), feeding
``planned_workouts`` (EC-02/EC-03). The original daily-sum fetcher,
``fetch_activity_calories_by_day``, was retired in EC-07 once
``get_effective_target`` was repointed at ``planned_workouts`` for
``calories_out`` — see ``api/app/domain/targets.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.domain.errors import IntervalsUnavailableError
from app.settings import settings

_INTERVALS_ACTIVITIES_URL = "https://intervals.icu/api/v1/athlete/{athlete_id}/activities"
_INTERVALS_EVENTS_URL = "https://intervals.icu/api/v1/athlete/{athlete_id}/events"
_INTERVALS_BASIC_AUTH_USERNAME = "API_KEY"
_INTERVALS_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=5.0)
_INTERVALS_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ActivityDetail:
    """One completed intervals.icu activity, unsummed.

    Feeds ``planned_workouts`` rows with ``status='completed'`` (EC-03).
    """

    external_id: str
    start_date_local: str
    duration_minutes: float | None
    sport_type: str | None
    calories: int | None


@dataclass(frozen=True)
class PlannedEventDetail:
    """One intervals.icu calendar event (typically a future planned workout).

    Feeds ``planned_workouts`` rows with ``status='planned'`` (EC-03).
    """

    external_id: str
    start_date_local: str
    duration_minutes: float | None
    sport_type: str | None
    icu_joules: float | None


def fetch_activities_detailed(
    *,
    oldest: date,
    newest: date,
    athlete_id: str | None = None,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> list[ActivityDetail]:
    """Fetch intervals activities (completed only) with per-activity detail.

    Keeps each activity's start time, duration, sport type, and calories
    instead of collapsing them into a daily sum. Feeds ``planned_workouts``
    rows with ``status='completed'``; ``calories`` here is also what
    ``get_effective_target`` sums to derive a day's ``calories_out`` (EC-07).

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

    payload = _get_json_with_retries(
        url=url,
        params=params,
        athlete_id=resolved_athlete_id,
        api_key=resolved_api_key,
        client=client,
    )
    return _parse_activities_detailed_payload(payload)


def fetch_planned_events(
    *,
    oldest: date,
    newest: date,
    athlete_id: str | None = None,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> list[PlannedEventDetail]:
    """Fetch intervals.icu calendar events (including future planned workouts).

    Same auth/timeout/retry shape as ``fetch_activities_detailed``, but
    hits the events endpoint. ``icu_joules`` is only present when the event
    has structured power/pace/HR targets and the athlete's zones are
    configured; it is passed through as ``None`` when absent. Feeds
    ``planned_workouts`` rows with ``status='planned'``.

    Raises:
        IntervalsUnavailableError: When the upstream call fails after bounded
        retries or returns malformed data.
    """

    if newest < oldest:
        raise ValueError("newest must be on or after oldest")

    resolved_athlete_id = athlete_id or settings.intervals_athlete_id
    resolved_api_key = api_key or settings.intervals_api_key
    url = _INTERVALS_EVENTS_URL.format(athlete_id=resolved_athlete_id)
    params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}

    payload = _get_json_with_retries(
        url=url,
        params=params,
        athlete_id=resolved_athlete_id,
        api_key=resolved_api_key,
        client=client,
    )
    return _parse_planned_events_payload(payload)


def _get_json_with_retries(
    *,
    url: str,
    params: dict[str, str],
    athlete_id: str,
    api_key: str,
    client: httpx.Client | None,
) -> Any:
    """Perform a GET with the shared bounded-retry/auth/timeout shape used by
    both ``fetch_activities_detailed`` and ``fetch_planned_events``, returning
    the parsed JSON body.

    Raises:
        IntervalsUnavailableError: When the upstream call fails after bounded
        retries or returns malformed JSON.
    """

    auth = (_INTERVALS_BASIC_AUTH_USERNAME, api_key)
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

            return response.json()

        raise IntervalsUnavailableError("intervals.icu sync failed.")
    except (ValueError, TypeError) as exc:
        raise IntervalsUnavailableError(
            "intervals.icu sync failed due to invalid response."
        ) from exc
    finally:
        if managed_client:
            http_client.close()


def _parse_activities_detailed_payload(payload: Any) -> list[ActivityDetail]:
    """Parse activities JSON payload into a list of ``ActivityDetail``."""

    if not isinstance(payload, list):
        raise ValueError("activities payload must be a list")

    details: list[ActivityDetail] = []
    for activity in payload:
        if not isinstance(activity, dict):
            raise ValueError("activity row must be an object")

        start_date_like = _first_present(activity, "start_date_local", "start_date", "date")
        if not isinstance(start_date_like, str):
            raise ValueError("activity row is missing start date")

        external_id = _extract_external_id(activity)
        duration_minutes = _extract_duration_minutes(activity)
        sport_type = _extract_sport_type(activity)
        calories = _extract_activity_calories(activity)

        details.append(
            ActivityDetail(
                external_id=external_id,
                start_date_local=start_date_like,
                duration_minutes=duration_minutes,
                sport_type=sport_type,
                calories=calories,
            )
        )

    return details


def _parse_planned_events_payload(payload: Any) -> list[PlannedEventDetail]:
    """Parse events JSON payload into a list of ``PlannedEventDetail``."""

    if not isinstance(payload, list):
        raise ValueError("events payload must be a list")

    details: list[PlannedEventDetail] = []
    for event in payload:
        if not isinstance(event, dict):
            raise ValueError("event row must be an object")

        start_date_like = _first_present(event, "start_date_local", "start_date", "date")
        if not isinstance(start_date_like, str):
            raise ValueError("event row is missing start date")

        external_id = _extract_external_id(event)
        duration_minutes = _extract_duration_minutes(event)
        sport_type = _extract_sport_type(event)
        icu_joules = _extract_icu_joules(event)

        details.append(
            PlannedEventDetail(
                external_id=external_id,
                start_date_local=start_date_like,
                duration_minutes=duration_minutes,
                sport_type=sport_type,
                icu_joules=icu_joules,
            )
        )

    return details


def _extract_external_id(row: dict[str, Any]) -> str:
    """Extract and stringify an activity/event's external id."""

    id_like = _first_present(row, "id", "icu_id")
    if id_like is None:
        raise ValueError("row is missing an id")
    return str(id_like)


def _extract_duration_minutes(row: dict[str, Any]) -> float | None:
    """Extract duration in minutes from seconds-based moving/elapsed time fields."""

    seconds = _first_present(row, "moving_time", "elapsed_time")
    if seconds is None:
        return None
    if isinstance(seconds, bool):
        raise TypeError("duration must not be boolean")
    return float(seconds) / 60.0


def _extract_sport_type(row: dict[str, Any]) -> str | None:
    """Extract the sport/activity type."""

    sport_type = _first_present(row, "type", "category")
    if sport_type is None:
        return None
    if not isinstance(sport_type, str):
        raise ValueError("sport type must be a string")
    return sport_type


def _extract_icu_joules(row: dict[str, Any]) -> float | None:
    """Extract intervals.icu's computed work estimate, when present."""

    joules = _first_present(row, "icu_joules")
    if joules is None:
        return None
    if isinstance(joules, bool):
        raise TypeError("icu_joules must not be boolean")
    return float(joules)


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
