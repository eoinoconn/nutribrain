"""intervals.icu sync worker and status (§8, T-061, T-045).

One shared function backs all three triggers (nightly cron, on-demand MCP
tool, dashboard button). It upserts ``planned_workouts`` rows for the synced
range (EC-03, §6 "Sync changes") via ``sync_planned_workouts``.
``get_effective_target`` (``app/domain/targets.py``) derives ``calories_out``
from those rows at read time (EC-07, "Reconciling calories-out") — this
module no longer independently syncs a same-day calories-out sum into
``intervals_calories_out``; that table now only holds manual-override rows
(``set_manual_calories_out`` below).

Each planned-workout row is written in its own savepoint so a failure on one
row doesn't lose the rest of the same-range sync — the range still fails
loudly if an upstream fetch itself fails (auth/network), since there is
nothing to write in that case. The single-row ``intervals_sync_status`` table
records the last outcome so the dashboard can show "last sync N hours ago" /
an error banner even for cron runs, which happen in a separate process from
the web dyno.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.db import IntervalsCaloriesOut, IntervalsSource, IntervalsSyncStatus, session_scope
from app.domain.dto import ManualCaloriesOutResult, SyncIntervalsResult, SyncStatus
from app.domain.planned_workouts import (
    FetchActivitiesDetailed,
    FetchPlannedEvents,
    sync_planned_workouts,
)
from app.intervals.client import fetch_activities_detailed, fetch_planned_events
from app.logging import get_logger

logger = get_logger(__name__)

StatusSessionFactory = Callable[[], AbstractContextManager[Session]]

_STATUS_ROW_ID = 1


def sync_intervals(
    session: Session,
    *,
    from_date: date,
    to_date: date,
    now: datetime | None = None,
    fetch_activities: FetchActivitiesDetailed = fetch_activities_detailed,
    fetch_planned: FetchPlannedEvents = fetch_planned_events,
    status_session_factory: StatusSessionFactory = session_scope,
) -> SyncIntervalsResult:
    """Sync ``planned_workouts`` for ``[from_date, to_date]`` inclusive.

    One shared function backs all three triggers (cron, the manual sync
    route, the MCP tool) via ``sync_planned_workouts``. ``get_effective_target``
    computes ``calories_out`` from the synced rows at read time (EC-07) — this
    function no longer writes ``intervals_calories_out`` itself (the old
    ``fetch_activity_calories_by_day`` daily-sum path is retired; that table
    is now written only by ``set_manual_calories_out``, for manual overrides).

    Raises whatever a fetch callable raises (``IntervalsUnavailableError`` on
    upstream failure) — there is nothing to write if the fetch itself failed,
    so that propagates uncaught, and the failure is recorded on the status
    row before re-raising. Per-row write failures instead are caught, logged,
    and appended to ``failures`` so the rest of the range still syncs; the
    sync as a whole still counts as successful for status purposes.

    ``status_session_factory`` defaults to a fresh, independently-committed
    session (see ``_record_sync_failure``) — tests override it to keep status
    writes inside the same rolled-back transaction as everything else.
    """

    if to_date < from_date:
        raise ValueError("to_date must be on or after from_date")

    resolved_now = now or datetime.now(UTC)

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

    _record_sync_success(status_session_factory, synced_at=resolved_now)

    logger.info(
        "intervals_sync_completed",
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        workouts_synced=workout_result.workouts_synced,
        failure_count=len(workout_result.failures),
    )

    return SyncIntervalsResult(
        from_date=from_date,
        to_date=to_date,
        days_synced=workout_result.workouts_synced,
        failures=workout_result.failures,
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
