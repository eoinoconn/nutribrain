"""Account-level app settings domain logic (§6a, EC-06).

Single-user app, no ``user_id`` — ``app_settings`` is a one-row singleton
table (id fixed at 1 by convention, mirroring ``IntervalsSyncStatus`` /
``app/domain/intervals_sync.py``, not a DB constraint). ``get_settings``
lazily creates the row with the default ``'UTC'`` on first read rather than
seeding it in the migration, so the same lazy-create pattern used by
``intervals_sync.py``'s status row is reused here instead of introducing a
second convention for singleton rows.

The energy chart (EC-05, not built yet) will call ``get_settings`` to resolve
local-midnight/end-of-day bounds for any day with no logged meal to infer a
timezone from (a ``Meal.local_tz`` value).
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.db import AppSettings
from app.domain.dto import AppSettingsDTO
from app.domain.errors import InvalidTimezoneError
from app.logging import get_logger

logger = get_logger(__name__)

_SETTINGS_ROW_ID = 1
_DEFAULT_TIMEZONE = "UTC"


def get_settings(session: Session) -> AppSettingsDTO:
    """Return the singleton settings row, creating it with defaults if absent."""

    row = session.get(AppSettings, _SETTINGS_ROW_ID)
    if row is None:
        row = AppSettings(id=_SETTINGS_ROW_ID, local_timezone=_DEFAULT_TIMEZONE)
        session.add(row)
        session.flush()
    return AppSettingsDTO(local_timezone=row.local_timezone)


def update_settings(session: Session, *, local_timezone: str) -> AppSettingsDTO:
    """Update the singleton settings row and return the new values.

    Raises ``InvalidTimezoneError`` if ``local_timezone`` isn't a valid IANA
    timezone name — a bad value here would silently break the energy chart's
    local-midnight bounds later, so it's rejected at write time instead.
    """

    try:
        ZoneInfo(local_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezoneError(local_timezone) from exc

    row = session.get(AppSettings, _SETTINGS_ROW_ID)
    if row is None:
        row = AppSettings(id=_SETTINGS_ROW_ID, local_timezone=local_timezone)
        session.add(row)
    else:
        row.local_timezone = local_timezone
    session.flush()

    logger.info("settings_updated", local_timezone=local_timezone)

    return AppSettingsDTO(local_timezone=local_timezone)
