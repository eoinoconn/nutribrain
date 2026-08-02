"""Tests for T-060 intervals.icu activities client.

These tests use recorded fixtures and mocked transports only (never live API).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.domain.errors import IntervalsUnavailableError
from app.intervals.client import (
    ActivityDetail,
    PlannedEventDetail,
    fetch_activities_detailed,
    fetch_activity_calories_by_day,
    fetch_planned_events,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "intervals"


def _load_fixture(name: str) -> list[dict[str, object]]:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_fetch_activity_calories_by_day_sums_activity_calories_by_day() -> None:
    payload = _load_fixture("activities_success.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/athlete/athlete-123/activities"
        assert request.url.params["oldest"] == "2026-07-20"
        assert request.url.params["newest"] == "2026-07-22"
        assert request.headers["Authorization"] == "Basic QVBJX0tFWTphcGkta2V5"
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_activity_calories_by_day(
        oldest=date(2026, 7, 20),
        newest=date(2026, 7, 22),
        athlete_id="athlete-123",
        api_key="api-key",
        client=client,
    )

    assert result == {
        date(2026, 7, 20): 800,
        date(2026, 7, 21): 0,
        date(2026, 7, 22): None,
    }


def test_fetch_activity_calories_by_day_retries_retryable_status_then_succeeds() -> None:
    payload = _load_fixture("activities_success.json")
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_activity_calories_by_day(
        oldest=date(2026, 7, 20),
        newest=date(2026, 7, 22),
        athlete_id="athlete-123",
        api_key="api-key",
        client=client,
    )

    assert calls == 3
    assert result[date(2026, 7, 20)] == 800


def test_fetch_activity_calories_by_day_uses_start_date_when_local_missing() -> None:
    payload = [
        {
            "id": "i10",
            "start_date": "2026-07-26T06:15:00Z",
            "type": "Ride",
            "calories": 420,
        }
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_activity_calories_by_day(
        oldest=date(2026, 7, 26),
        newest=date(2026, 7, 26),
        athlete_id="athlete-123",
        api_key="api-key",
        client=client,
    )

    assert result == {date(2026, 7, 26): 420}


def test_fetch_activity_calories_by_day_raises_intervals_unavailable_after_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(IntervalsUnavailableError) as exc_info:
        fetch_activity_calories_by_day(
            oldest=date(2026, 7, 20),
            newest=date(2026, 7, 23),
            athlete_id="athlete-123",
            api_key="api-key",
            client=client,
        )

    assert calls == 3
    assert exc_info.value.error == "intervals_unavailable"


# --- fetch_activities_detailed -----------------------------------------------


def test_fetch_activities_detailed_returns_per_activity_records() -> None:
    payload = _load_fixture("activities_detailed_success.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/athlete/athlete-123/activities"
        assert request.url.params["oldest"] == "2026-07-20"
        assert request.url.params["newest"] == "2026-07-22"
        assert request.headers["Authorization"] == "Basic QVBJX0tFWTphcGkta2V5"
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_activities_detailed(
        oldest=date(2026, 7, 20),
        newest=date(2026, 7, 22),
        athlete_id="athlete-123",
        api_key="api-key",
        client=client,
    )

    assert result == [
        ActivityDetail(
            external_id="i1",
            start_date_local="2026-07-20T08:15:00",
            duration_minutes=60.0,
            sport_type="Run",
            calories=500,
        ),
        ActivityDetail(
            external_id="i2",
            start_date_local="2026-07-21T18:30:00",
            duration_minutes=30.0,
            sport_type="Ride",
            calories=300,
        ),
        ActivityDetail(
            external_id="i3",
            start_date_local="2026-07-22T07:00:00",
            duration_minutes=None,
            sport_type="Walk",
            calories=None,
        ),
    ]


def test_fetch_activities_detailed_returns_empty_list_for_empty_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_activities_detailed(
        oldest=date(2026, 7, 20),
        newest=date(2026, 7, 22),
        athlete_id="athlete-123",
        api_key="api-key",
        client=client,
    )

    assert result == []


def test_fetch_activities_detailed_raises_intervals_unavailable_after_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(IntervalsUnavailableError) as exc_info:
        fetch_activities_detailed(
            oldest=date(2026, 7, 20),
            newest=date(2026, 7, 23),
            athlete_id="athlete-123",
            api_key="api-key",
            client=client,
        )

    assert calls == 3
    assert exc_info.value.error == "intervals_unavailable"


# --- fetch_planned_events -----------------------------------------------------


def test_fetch_planned_events_returns_per_event_records() -> None:
    payload = _load_fixture("planned_events_success.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/athlete/athlete-123/events"
        assert request.url.params["oldest"] == "2026-08-01"
        assert request.url.params["newest"] == "2026-08-10"
        assert request.headers["Authorization"] == "Basic QVBJX0tFWTphcGkta2V5"
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_planned_events(
        oldest=date(2026, 8, 1),
        newest=date(2026, 8, 10),
        athlete_id="athlete-123",
        api_key="api-key",
        client=client,
    )

    assert result == [
        PlannedEventDetail(
            external_id="e1",
            start_date_local="2026-08-05T06:00:00",
            duration_minutes=90.0,
            sport_type="Ride",
            icu_joules=2100000.0,
        ),
        PlannedEventDetail(
            external_id="e2",
            start_date_local="2026-08-06T17:00:00",
            duration_minutes=40.0,
            sport_type="Run",
            icu_joules=None,
        ),
    ]


def test_fetch_planned_events_returns_empty_list_for_empty_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_planned_events(
        oldest=date(2026, 8, 1),
        newest=date(2026, 8, 10),
        athlete_id="athlete-123",
        api_key="api-key",
        client=client,
    )

    assert result == []


def test_fetch_planned_events_raises_intervals_unavailable_after_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(IntervalsUnavailableError) as exc_info:
        fetch_planned_events(
            oldest=date(2026, 8, 1),
            newest=date(2026, 8, 10),
            athlete_id="athlete-123",
            api_key="api-key",
            client=client,
        )

    assert calls == 3
    assert exc_info.value.error == "intervals_unavailable"
