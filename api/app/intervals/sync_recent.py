"""Cron entrypoint for the nightly intervals.icu sync (T-062, §8, §10).

Invoked as ``python -m app.intervals.sync_recent`` by the Render cron job.
Syncs ``INTERVALS_SYNC_DAYS`` days (default 3) ending yesterday — today is
excluded because intervals.icu typically hasn't finished processing the
current day's activities by 03:00 UTC. Exits non-zero only when the sync
fails outright (fetch/auth/network failure), so Render's cron monitor
surfaces the run as failed. Per-day write failures are logged but don't
fail the run, matching ``sync_intervals``'s "isolate one bad day" behavior.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta

from app.db import session_scope
from app.domain import get_settings, parse_local_date, sync_intervals
from app.domain.errors import DomainError
from app.domain.intervals_sync import StatusSessionFactory
from app.logging import configure_logging, get_logger
from app.settings import settings

configure_logging(settings.log_level)
logger = get_logger(__name__)


def main(
    *,
    session_factory: StatusSessionFactory = session_scope,
    now: datetime | None = None,
) -> int:
    started = time.monotonic()
    try:
        with session_factory() as session:
            local_tz = get_settings(session).local_timezone
            today = parse_local_date("today", local_tz=local_tz, now=now)
            to_date = today - timedelta(days=1)
            from_date = to_date - timedelta(days=settings.intervals_sync_days - 1)
            result = sync_intervals(session, from_date=from_date, to_date=to_date)
    except DomainError as exc:
        logger.error(
            "intervals_cron_sync_failed",
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            duration_s=round(time.monotonic() - started, 3),
            error=str(exc),
        )
        return 1

    logger.info(
        "intervals_cron_sync_completed",
        from_date=result.from_date.isoformat(),
        to_date=result.to_date.isoformat(),
        days_synced=result.days_synced,
        failure_count=len(result.failures),
        duration_s=round(time.monotonic() - started, 3),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
