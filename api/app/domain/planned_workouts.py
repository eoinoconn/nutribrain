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

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db import PlannedWorkout, PlannedWorkoutSource, PlannedWorkoutStatus
from app.domain.dto import PlannedWorkoutDTO
from app.domain.errors import NaiveDatetimeError
from app.domain.settings import get_settings
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
