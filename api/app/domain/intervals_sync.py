"""intervals.icu sync worker (§8, T-061).

One shared function backs all three triggers (nightly cron, on-demand MCP
tool, dashboard button). Missing-data rules are load-bearing: a ``None`` day
from the client writes no row ("no data"); a ``0`` day writes a genuine zero
(a rest day). Getting this backwards silently corrupts every effective
target computed from the cache.

Each day is written in its own savepoint so a failure on one day doesn't
lose already-synced days in the same range — the range still fails loudly
if the upstream fetch itself fails (auth/network), since there is nothing
to write in that case.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.db import IntervalsCaloriesOut, IntervalsSource
from app.domain.dto import SyncIntervalsResult
from app.intervals.client import fetch_activity_calories_by_day
from app.logging import get_logger

logger = get_logger(__name__)

FetchCaloriesByDay = Callable[..., dict[date, int | None]]


def sync_intervals(
    session: Session,
    *,
    from_date: date,
    to_date: date,
    now: datetime | None = None,
    fetch: FetchCaloriesByDay = fetch_activity_calories_by_day,
) -> SyncIntervalsResult:
    """Sync calories-out for ``[from_date, to_date]`` inclusive.

    Raises whatever the fetch callable raises (``IntervalsUnavailableError``
    on upstream failure) — there is nothing to write if the fetch itself
    failed, so that propagates uncaught. Per-day write failures instead are
    caught, logged, and recorded in the result so the rest of the range
    still syncs.
    """

    if to_date < from_date:
        raise ValueError("to_date must be on or after from_date")

    resolved_now = now or datetime.now(UTC)
    calories_by_day = fetch(oldest=from_date, newest=to_date)

    days_synced = 0
    failures: list[dict[str, object]] = []

    day = from_date
    while day <= to_date:
        calories_out = calories_by_day.get(day)
        if calories_out is not None:
            try:
                with session.begin_nested():
                    _upsert_calories_out(
                        session,
                        day=day,
                        calories_out=calories_out,
                        fetched_at=resolved_now,
                    )
                days_synced += 1
            except Exception as exc:  # isolate one bad day, keep syncing the rest
                logger.warning(
                    "intervals_sync_day_failed",
                    date=day.isoformat(),
                    error=str(exc),
                )
                failures.append({"date": day.isoformat(), "error": str(exc)})
        day += timedelta(days=1)

    logger.info(
        "intervals_sync_completed",
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        days_synced=days_synced,
        failure_count=len(failures),
    )

    return SyncIntervalsResult(
        from_date=from_date,
        to_date=to_date,
        days_synced=days_synced,
        failures=failures,
    )


def _upsert_calories_out(
    session: Session,
    *,
    day: date,
    calories_out: int,
    fetched_at: datetime,
) -> None:
    """Write one day's cache row, replacing any manual override (§8, G5)."""

    row = session.get(IntervalsCaloriesOut, day)
    if row is None:
        row = IntervalsCaloriesOut(
            date=day,
            calories_out=calories_out,
            fetched_at=fetched_at,
            source=IntervalsSource.sync,
        )
        session.add(row)
    else:
        row.calories_out = calories_out
        row.fetched_at = fetched_at
        row.source = IntervalsSource.sync
    session.flush()
