"""Manual planned-workout entry (EC-04, §6 "Manual fallback").

`create_manual_planned_workout` is a lightweight "plan a workout" input
(start time + estimated kcal, `source='manual'`) for days without an
intervals.icu event, so a future fueling indicator (EC-05) isn't hard-blocked
on intervals.icu having the session scheduled. It writes a normal
`planned_workouts` row — there's no separate "manual workouts" table or
parallel storage, so any future query against `planned_workouts` filtered by
`local_date` picks up a manual row identically to a synced one (EC-02/EC-03).

Not a full workout editor: no sport type, structured targets, or intervals.icu
linkage — those fields are simply None/absent for manual rows, matching the
`PlannedWorkout` model's column comments (`app/db/models.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import PlannedWorkout, PlannedWorkoutSource, PlannedWorkoutStatus
from app.domain.dto import PlannedWorkoutDTO
from app.domain.energy_balance import estimate_workout_calories
from app.domain.errors import NaiveDatetimeError
from app.domain.settings import get_settings
from app.intervals.client import (
    ActivityDetail,
    PlannedEventDetail,
    fetch_activities_detailed,
    fetch_planned_events,
)
from app.logging import get_logger

logger = get_logger(__name__)

# The spec text (§6) only calls for "start time + estimated kcal" — duration
# isn't mentioned, but the `planned_workouts.duration_minutes` column is
# NOT NULL (EC-01). Rather than force the small manual-entry form to also
# collect a duration, default to a round hour, matching a typical single
# workout session; callers that do know a real duration can still pass one.
DEFAULT_DURATION_MINUTES = 60


def create_manual_planned_workout(
    session: Session,
    *,
    start_at: datetime,
    estimated_calories: int,
    duration_minutes: int | None = None,
    now: datetime | None = None,
) -> PlannedWorkoutDTO:
    """Insert a `source='manual'`, `status='planned'` planned_workouts row.

    `local_date` is derived from `start_at` converted into the account's
    configured local timezone (`app/domain/settings.py`'s `get_settings`,
    EC-06) — the same "whose midnight is this" source of truth the energy
    chart (EC-05) is documented to use, since `planned_workouts` (unlike
    `meals`) has no per-row `local_tz` column to derive it from instead.

    Args:
        session: Active SQLAlchemy session.
        start_at: Timezone-aware start time for the planned workout.
        estimated_calories: Caller-supplied estimated kcal for the session.
        duration_minutes: Optional duration; defaults to
            `DEFAULT_DURATION_MINUTES` (see module docstring).
        now: Timezone-aware "now" for `fetched_at` (defaults to UTC now).

    Returns:
        PlannedWorkoutDTO for the newly created row.

    Raises:
        NaiveDatetimeError: If `start_at` is not timezone-aware.
    """

    if start_at.tzinfo is None:
        raise NaiveDatetimeError(field="start_at")

    app_settings = get_settings(session)
    local_dt = start_at.astimezone(ZoneInfo(app_settings.local_timezone))
    local_date = local_dt.date()

    resolved_duration_minutes = (
        duration_minutes if duration_minutes is not None else DEFAULT_DURATION_MINUTES
    )
    workout = PlannedWorkout(
        external_id=None,
        source=PlannedWorkoutSource.manual,
        local_date=local_date,
        start_at=start_at,
        duration_minutes=resolved_duration_minutes,
        sport_type=None,
        icu_joules=None,
        estimated_calories=estimated_calories,
        actual_calories=None,
        status=PlannedWorkoutStatus.planned,
        fetched_at=now or datetime.now(UTC),
    )
    session.add(workout)
    session.flush()

    logger.info(
        "planned_workout_created_manual",
        planned_workout_id=workout.id,
        local_date=str(local_date),
    )

    return PlannedWorkoutDTO(
        id=workout.id,
        external_id=workout.external_id,
        source=workout.source,
        local_date=workout.local_date,
        start_at=workout.start_at,
        duration_minutes=workout.duration_minutes,
        sport_type=workout.sport_type,
        icu_joules=workout.icu_joules,
        estimated_calories=workout.estimated_calories,
        actual_calories=workout.actual_calories,
        status=workout.status,
        fetched_at=workout.fetched_at,
    )


def _to_dto(workout: PlannedWorkout) -> PlannedWorkoutDTO:
    return PlannedWorkoutDTO(
        id=workout.id,
        external_id=workout.external_id,
        source=workout.source,
        local_date=workout.local_date,
        start_at=workout.start_at,
        duration_minutes=workout.duration_minutes,
        sport_type=workout.sport_type,
        icu_joules=workout.icu_joules,
        estimated_calories=workout.estimated_calories,
        actual_calories=workout.actual_calories,
        status=workout.status,
        fetched_at=workout.fetched_at,
    )


def list_planned_workouts_for_day(session: Session, *, day: date) -> list[PlannedWorkoutDTO]:
    """List every planned_workouts row (any source/status) for one local day.

    Ordered by start_at so a caller (e.g. get_day, EC-04's list-alongside-
    meals surface) can render them chronologically without re-sorting.
    """

    workouts = session.scalars(
        select(PlannedWorkout)
        .where(PlannedWorkout.local_date == day)
        .order_by(PlannedWorkout.start_at)
    )
    return [_to_dto(workout) for workout in workouts]


# --- EC-03: sync-side mapping + upsert (§6 "Sync changes") -----------------
#
# KCAL_PER_KILOJOULE / estimate_workout_calories now live in
# `api/app/domain/energy_balance.py`, per the spec's §6/"Workout calorie
# estimation" section — relocated here by EC-05 once that module existed
# (see this module's git history for the original parked implementation).

FetchActivitiesDetailed = Callable[..., list[ActivityDetail]]
FetchPlannedEvents = Callable[..., list[PlannedEventDetail]]

# `duration_minutes` is NOT NULL on the model (EC-01), but the client
# dataclasses report `float | None` (intervals.icu sometimes omits
# moving_time/elapsed_time). Falling back to 0 rather than skipping the row
# entirely or guessing a duration — 0 is honest ("we don't know"), keeps the
# row syncing (so it can still flip to completed / carry actual_calories
# later), and doesn't silently invent a duration that would mislead any
# future duration-based UI.
_FALLBACK_DURATION_MINUTES = 0


@dataclass(frozen=True, slots=True)
class PlannedWorkoutsSyncResult:
    """Result of one ``sync_planned_workouts`` invocation (EC-03/EC-12)."""

    workouts_synced: int
    failures: list[dict[str, object]]
    stale_planned_removed: int = 0


def sync_planned_workouts(
    session: Session,
    *,
    from_date: date,
    to_date: date,
    now: datetime | None = None,
    fetch_activities: FetchActivitiesDetailed = fetch_activities_detailed,
    fetch_planned: FetchPlannedEvents = fetch_planned_events,
) -> PlannedWorkoutsSyncResult:
    """Upsert ``planned_workouts`` rows from both intervals.icu client calls.

    Keyed on ``(source, external_id)`` per the table's unique constraint
    (EC-01). Each row is written in its own savepoint so one bad row doesn't
    lose the rest of the batch — mirrors ``intervals_sync.sync_intervals``'s
    per-day isolation. Upstream fetch failures are NOT caught here; they
    propagate to the caller (``sync_intervals``), which records sync status
    and re-raises, matching the "nothing to write if the fetch itself
    failed" rule the calories-out sync already follows.

    Planned -> completed correlation: EC-03 originally guessed that a
    completed activity's own id could reappear as a planned event's id
    across the two endpoints — confirmed wrong in practice (intervals.icu
    gave a real calendar entry and its resulting activity two unrelated ids,
    leaving both a stale "planned" row and a separate "completed" row
    visible at once). The vendored OpenAPI spec (``openapi-spec (3).json``,
    ``Activity.paired_event_id``) documents the actual link: a completed
    activity carries the *event's own* ``id`` (not the event's
    ``external_id`` field — intervals.icu's ``Event.id``, which is what this
    codebase already stores as a planned row's ``external_id``) in
    ``paired_event_id``. This function resolves the "Done when" flip
    requirement as follows:

    - When a completed activity's ``paired_event_id`` matches an existing
      ``(intervals_planned, external_id)`` row, that row is updated in
      place: its ``source`` flips to ``intervals_completed``, ``status`` to
      ``completed``, ``actual_calories`` is set, ``icu_joules``/
      ``estimated_calories`` are cleared (per the mapping table: completed
      rows always carry null ``icu_joules``/``estimated_calories``, since
      that endpoint never returns ``icu_joules``), ``external_id`` is
      rewritten to the *activity's own* id (so the row is identifiable via
      its real intervals.icu activity going forward — e.g. a
      ``/activities/{external_id}`` link — and so a later re-sync of this
      same activity finds it again via the ordinary same-source lookup), and
      ``paired_event_id`` is kept, preserving the link back to the original
      event so a later ``/events`` sync can still recognize it as completed
      (see the next bullet). This is an UPDATE that changes the unique key's
      ``source`` value, not a same-source upsert — deliberately, so no stale
      planned duplicate is left behind next to a new completed row for the
      same real-world workout.
    - When a planned event's own id matches an existing
      ``(intervals_completed, paired_event_id)`` row, the planned-side
      upsert is skipped entirely — an already-completed row is never
      retroactively downgraded back to ``planned`` just because a re-sync of
      ``/events`` still (or again) returns that event.
    - A planned event whose id disappears from a later ``/events`` response
      within the synced range (removed, or completed upstream and already
      flipped by the branch above) is deleted: a still-``status='planned'``
      row for that range with no matching id in this fetch means intervals.icu
      no longer has that session scheduled, so the app shouldn't either
      (EC-12). Only ``source='intervals_planned'`` rows are eligible — a
      manual (§6 fallback) row is never touched by this sync, and a row
      already flipped to ``intervals_completed`` is a different source and
      excluded by construction. Scoped to ``[from_date, to_date]``: this sync
      only has fresh data for that window, so a planned row outside it is
      left alone regardless of whether this fetch mentions it.
    """

    resolved_now = now or datetime.now(UTC)
    app_settings = get_settings(session)
    local_timezone = app_settings.local_timezone

    activities = fetch_activities(oldest=from_date, newest=to_date)
    planned_events = fetch_planned(oldest=from_date, newest=to_date)

    workouts_synced = 0
    failures: list[dict[str, object]] = []

    for activity in activities:
        try:
            with session.begin_nested():
                _upsert_completed_activity(
                    session,
                    activity=activity,
                    now=resolved_now,
                    local_timezone=local_timezone,
                )
            workouts_synced += 1
        except Exception as exc:  # isolate one bad row, keep syncing the rest
            logger.warning(
                "planned_workout_sync_activity_failed",
                external_id=activity.external_id,
                error=str(exc),
            )
            failures.append(
                {
                    "source": PlannedWorkoutSource.intervals_completed.value,
                    "external_id": activity.external_id,
                    "error": str(exc),
                }
            )

    for event in planned_events:
        try:
            with session.begin_nested():
                _upsert_planned_event(
                    session,
                    event=event,
                    now=resolved_now,
                    local_timezone=local_timezone,
                )
            workouts_synced += 1
        except Exception as exc:  # isolate one bad row, keep syncing the rest
            logger.warning(
                "planned_workout_sync_event_failed",
                external_id=event.external_id,
                error=str(exc),
            )
            failures.append(
                {
                    "source": PlannedWorkoutSource.intervals_planned.value,
                    "external_id": event.external_id,
                    "error": str(exc),
                }
            )

    synced_external_ids = {event.external_id for event in planned_events}
    stale_planned = session.scalars(
        select(PlannedWorkout).where(
            PlannedWorkout.source == PlannedWorkoutSource.intervals_planned,
            PlannedWorkout.status == PlannedWorkoutStatus.planned,
            PlannedWorkout.local_date >= from_date,
            PlannedWorkout.local_date <= to_date,
            PlannedWorkout.external_id.notin_(synced_external_ids),
        )
    ).all()
    for row in stale_planned:
        logger.info(
            "planned_workout_removed_stale",
            planned_workout_id=row.id,
            external_id=row.external_id,
        )
        session.delete(row)
    if stale_planned:
        session.flush()

    logger.info(
        "planned_workouts_sync_completed",
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        workouts_synced=workouts_synced,
        failure_count=len(failures),
        stale_planned_removed=len(stale_planned),
    )

    return PlannedWorkoutsSyncResult(
        workouts_synced=workouts_synced,
        failures=failures,
        stale_planned_removed=len(stale_planned),
    )


def _upsert_completed_activity(
    session: Session,
    *,
    activity: ActivityDetail,
    now: datetime,
    local_timezone: str,
) -> None:
    """Upsert one completed-activity row, flipping a matching planned row.

    See ``sync_planned_workouts``'s docstring for the planned -> completed
    correlation rationale.
    """

    local_date, start_at = _parse_local_datetime(
        activity.start_date_local, local_timezone=local_timezone
    )
    duration_minutes = (
        round(activity.duration_minutes)
        if activity.duration_minutes is not None
        else _FALLBACK_DURATION_MINUTES
    )

    planned_match = None
    if activity.paired_event_id is not None:
        planned_match = session.scalar(
            select(PlannedWorkout).where(
                PlannedWorkout.source == PlannedWorkoutSource.intervals_planned,
                PlannedWorkout.external_id == activity.paired_event_id,
            )
        )
    # Idempotent re-sync of this same completed activity (not a
    # planned->completed flip -- the row is already `intervals_completed`).
    completed_match = session.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.source == PlannedWorkoutSource.intervals_completed,
            PlannedWorkout.external_id == activity.external_id,
        )
    )

    if planned_match is not None and completed_match is not None:
        # Both exist for the same real workout -- e.g. left over from before
        # paired_event_id-based correlation existed (this activity was
        # synced once already under the old same-external_id guess, which
        # never matched, so it got its own row; the original planned row
        # from /events was never flipped and is only now findable via
        # paired_event_id). Repurposing `planned_match` into a completed row
        # here would collide with `completed_match`'s existing
        # (source, external_id) key, so consolidate onto the already-
        # completed row instead and drop the now-redundant planned one.
        logger.info(
            "planned_workout_consolidated_duplicate",
            kept_id=completed_match.id,
            removed_id=planned_match.id,
        )
        session.delete(planned_match)
        session.flush()
        row: PlannedWorkout | None = completed_match
    else:
        row = planned_match or completed_match

    if row is None:
        row = PlannedWorkout(external_id=activity.external_id)
        session.add(row)

    row.source = PlannedWorkoutSource.intervals_completed
    # When this row was found via paired_event_id, it still carries the
    # planned event's own id (from before the flip) -- rewrite it to the
    # activity's own external_id so a later re-sync of the same activity
    # finds this row via the idempotent-resync lookup above (which matches
    # on the activity's external_id, not the original event's) instead of
    # creating a duplicate.
    row.external_id = activity.external_id
    # Preserved separately from external_id (which just got overwritten
    # above) so `_upsert_planned_event` can still recognize "this event has
    # already been completed" on a later /events sync.
    row.paired_event_id = activity.paired_event_id
    row.local_date = local_date
    row.start_at = start_at
    row.duration_minutes = duration_minutes
    row.sport_type = activity.sport_type
    # Completed rows never carry icu_joules (not returned by the activities
    # endpoint) or estimated_calories (planned-only field) -- see the
    # mapping table in the EC-03 task brief.
    row.icu_joules = None
    row.estimated_calories = None
    row.actual_calories = activity.calories
    row.status = PlannedWorkoutStatus.completed
    row.fetched_at = now
    session.flush()


def _upsert_planned_event(
    session: Session,
    *,
    event: PlannedEventDetail,
    now: datetime,
    local_timezone: str,
) -> None:
    """Upsert one planned-event row, skipping ids already flipped to completed.

    See ``sync_planned_workouts``'s docstring for the planned -> completed
    correlation rationale. Matches on ``paired_event_id`` (not
    ``external_id``): a completed row's ``external_id`` is rewritten to the
    activity's own id when it's flipped (``_upsert_completed_activity``),
    so the *original* event's id only survives on ``paired_event_id``.
    """

    already_completed = session.scalar(
        select(PlannedWorkout.id).where(
            PlannedWorkout.source == PlannedWorkoutSource.intervals_completed,
            PlannedWorkout.paired_event_id == event.external_id,
        )
    )
    if already_completed is not None:
        return

    local_date, start_at = _parse_local_datetime(
        event.start_date_local, local_timezone=local_timezone
    )
    duration_minutes = (
        round(event.duration_minutes)
        if event.duration_minutes is not None
        else _FALLBACK_DURATION_MINUTES
    )
    icu_joules = round(event.icu_joules) if event.icu_joules is not None else None
    estimated_calories = estimate_workout_calories(icu_joules) if icu_joules is not None else None

    row = session.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.source == PlannedWorkoutSource.intervals_planned,
            PlannedWorkout.external_id == event.external_id,
        )
    )
    if row is None:
        row = PlannedWorkout(
            external_id=event.external_id,
            source=PlannedWorkoutSource.intervals_planned,
        )
        session.add(row)

    row.local_date = local_date
    row.start_at = start_at
    row.duration_minutes = duration_minutes
    row.sport_type = event.sport_type
    row.icu_joules = icu_joules
    row.estimated_calories = estimated_calories
    row.actual_calories = None
    row.status = PlannedWorkoutStatus.planned
    row.fetched_at = now
    session.flush()


def _parse_local_datetime(value: str, *, local_timezone: str) -> tuple[date, datetime]:
    """Parse an intervals.icu ``start_date_local`` string into a local date
    and a tz-aware ``start_at``.

    Unlike ``start_at`` on a manual row (a caller-supplied instant later
    converted *into* the account timezone to derive ``local_date``),
    intervals.icu's ``start_date_local`` is already local wall-clock time
    with no UTC offset (confirmed by reading
    ``client._extract_activity_day``, which treats the same field as a bare
    local date via ``date.fromisoformat(value[:10])``). There's no existing
    "attach a timezone to a naive intervals timestamp" convention elsewhere
    in this codebase to follow, so this attaches the account's configured
    local timezone (``app/domain/settings.py``) to the naive value to
    produce a tz-aware instant for the ``start_at`` column, while
    ``local_date`` is taken directly from the string's date component (no
    tz conversion needed since it's already local).
    """

    local_date = date.fromisoformat(value[:10])
    naive_dt = datetime.fromisoformat(value)
    start_at = naive_dt.replace(tzinfo=ZoneInfo(local_timezone))
    return local_date, start_at
