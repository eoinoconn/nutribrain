"""intervals.icu sync worker and status (§8, T-061, T-045).

One shared function backs all three triggers (nightly cron, on-demand MCP
tool, dashboard button). Missing-data rules are load-bearing: a ``None`` day
from the client writes no row ("no data"); a ``0`` day writes a genuine zero
(a rest day). Getting this backwards silently corrupts every effective
target computed from the cache.

Each day is written in its own savepoint so a failure on one day doesn't
lose already-synced days in the same range — the range still fails loudly
if the upstream fetch itself fails (auth/network), since there is nothing
to write in that case. The single-row ``intervals_sync_status`` table records
the last outcome so the dashboard can show "last sync N hours ago" / an error
banner even for cron runs, which happen in a separate process from the web
dyno.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.db import IntervalsCaloriesOut, IntervalsSource, IntervalsSyncStatus, session_scope
from app.domain.dto import ManualCaloriesOutResult, SyncIntervalsResult, SyncStatus
from app.domain.planned_workouts import (
    FetchActivitiesDetailed,
    FetchPlannedEvents,
    sync_planned_workouts,
)
from app.intervals.client import (
    fetch_activities_detailed,
    fetch_activity_calories_by_day,
    fetch_planned_events,
)
from app.logging import get_logger

logger = get_logger(__name__)

FetchCaloriesByDay = Callable[..., dict[date, int | None]]
StatusSessionFactory = Callable[[], AbstractContextManager[Session]]

_STATUS_ROW_ID = 1


def sync_intervals(
    session: Session,
    *,
    from_date: date,
    to_date: date,
    now: datetime | None = None,
    fetch: FetchCaloriesByDay = fetch_activity_calories_by_day,
    fetch_activities: FetchActivitiesDetailed = fetch_activities_detailed,
    fetch_planned: FetchPlannedEvents = fetch_planned_events,
    status_session_factory: StatusSessionFactory = session_scope,
) -> SyncIntervalsResult:
    """Sync calories-out for ``[from_date, to_date]`` inclusive.

    Also upserts ``planned_workouts`` rows for the same range (EC-03, §6
    "Sync changes") via ``sync_planned_workouts`` — one shared function backs
    all three triggers (cron, the manual sync route, the MCP tool), so
    extending this function in place, rather than adding a sibling the
    triggers would each need to call separately, keeps that "one function,
    three callers" property intact instead of duplicating the wiring three
    times. Does **not** yet touch ``intervals_calories_out`` or retire the
    old calories-out fetch (that's EC-07) — the two sync paths run
    side-by-side in this task.

    Raises whatever the fetch callable raises (``IntervalsUnavailableError``
    on upstream failure) — there is nothing to write if the fetch itself
    failed, so that propagates uncaught, and the failure is recorded on the
    status row before re-raising. Per-day write failures instead are caught,
    logged, and recorded in the result so the rest of the range still syncs;
    the sync as a whole still counts as successful for status purposes. The
    same applies to the planned-workouts fetch calls (propagate uncaught,
    recorded on the status row) and per-row write failures (caught, logged,
    appended to ``failures``).

    ``status_session_factory`` defaults to a fresh, independently-committed
    session (see ``_record_sync_failure``) — tests override it to keep status
    writes inside the same rolled-back transaction as everything else.
    """

    if to_date < from_date:
        raise ValueError("to_date must be on or after from_date")

    resolved_now = now or datetime.now(UTC)

    try:
        calories_by_day = fetch(oldest=from_date, newest=to_date)
    except Exception as exc:
        _record_sync_failure(status_session_factory, error=str(exc))
        raise

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
                        source=IntervalsSource.sync,
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

    try:
        workout_result = sync_planned_workouts(
            session,
            from_date=from_date,
            to_date=to_date,
            now=resolved_now,
            fetch_activities=fetch_activities,
            fetch_planned=fetch_planned,
        )
    except Exception as exc:
        _record_sync_failure(status_session_factory, error=str(exc))
        raise
    failures.extend(workout_result.failures)

    _record_sync_success(status_session_factory, synced_at=resolved_now)

    logger.info(
        "intervals_sync_completed",
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        days_synced=days_synced,
        workouts_synced=workout_result.workouts_synced,
        failure_count=len(failures),
    )

    return SyncIntervalsResult(
        from_date=from_date,
        to_date=to_date,
        days_synced=days_synced,
        failures=failures,
    )


def get_sync_status(session: Session) -> SyncStatus:
    """Return the last sync_intervals outcome, or an all-None status if never run."""

    row = session.get(IntervalsSyncStatus, _STATUS_ROW_ID)
    if row is None:
        return SyncStatus(last_synced_at=None, last_error=None)
    return SyncStatus(last_synced_at=row.last_synced_at, last_error=row.last_error)


def set_manual_calories_out(
    session: Session,
    *,
    day: date,
    calories_out: int,
    now: datetime | None = None,
) -> ManualCaloriesOutResult:
    """Record a manual calories-out override for ``day`` (§8 "Manual override", G5).

    The next real sync overwrites this and resets ``source`` back to
    ``sync`` — that is the desired behaviour, not a bug to guard against.
    """

    resolved_now = now or datetime.now(UTC)
    _upsert_calories_out(
        session,
        day=day,
        calories_out=calories_out,
        fetched_at=resolved_now,
        source=IntervalsSource.manual,
    )
    logger.info("intervals_manual_override_set", date=day.isoformat())
    return ManualCaloriesOutResult(date=day, calories_out=calories_out, fetched_at=resolved_now)


def _upsert_calories_out(
    session: Session,
    *,
    day: date,
    calories_out: int,
    fetched_at: datetime,
    source: IntervalsSource,
) -> None:
    """Write one day's cache row, overwriting whatever was there before."""

    row = session.get(IntervalsCaloriesOut, day)
    if row is None:
        row = IntervalsCaloriesOut(
            date=day,
            calories_out=calories_out,
            fetched_at=fetched_at,
            source=source,
        )
        session.add(row)
    else:
        row.calories_out = calories_out
        row.fetched_at = fetched_at
        row.source = source
    session.flush()


def _record_sync_success(factory: StatusSessionFactory, *, synced_at: datetime) -> None:
    """Persist success on its own connection, independent of the caller's session.

    The failure counterpart below writes from inside an ``except`` block
    whose exception is about to roll back the caller's transaction — writing
    status on the caller's session would roll back with it. The default
    factory (``session_scope``) commits immediately regardless, and keeps
    both paths consistent.
    """

    with factory() as status_session:
        row = status_session.get(IntervalsSyncStatus, _STATUS_ROW_ID)
        if row is None:
            status_session.add(
                IntervalsSyncStatus(id=_STATUS_ROW_ID, last_synced_at=synced_at, last_error=None)
            )
        else:
            row.last_synced_at = synced_at
            row.last_error = None


def _record_sync_failure(factory: StatusSessionFactory, *, error: str) -> None:
    with factory() as status_session:
        row = status_session.get(IntervalsSyncStatus, _STATUS_ROW_ID)
        if row is None:
            status_session.add(
                IntervalsSyncStatus(id=_STATUS_ROW_ID, last_synced_at=None, last_error=error)
            )
        else:
            row.last_error = error
