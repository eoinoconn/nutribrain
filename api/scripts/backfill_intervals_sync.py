#!/usr/bin/env python3
"""Resync ``planned_workouts`` for a historical date range from intervals.icu.

``get_effective_target`` derives ``calories_out`` from ``planned_workouts``
at read time (EC-07, ``app/domain/intervals_sync.py``); there is no longer a
separate daily calories-out sum stored independently. That means any gap in
``planned_workouts`` — e.g. rows deleted, or a day the nightly cron never
reached (it only looks back ``INTERVALS_SYNC_DAYS`` days, 3 by default,
``render.yaml``) — makes those days' effective targets look like they assume
zero exercise, understating the calorie allowance and making meals look like
they exceeded target.

The existing sync entry points (dashboard "sync now" button, MCP tool, the
nightly cron) all call ``sync_intervals`` with a fixed range — the manual
route hardcodes ``from_date=to_date=today`` (``app/api/sync.py``) — so none
of them can repair an older gap. This script calls the same domain function
directly with an arbitrary range, sourcing from intervals.icu (the external
system of record for this data), which is safe to rerun: ``sync_planned_workouts``
upserts on ``(source, external_id)``, so re-syncing an already-synced day is a
no-op change, not a duplicate.

Usage:
  uv run --project api python api/scripts/backfill_intervals_sync.py \
      --from 2026-07-24 --to 2026-08-03
  uv run --project api python api/scripts/backfill_intervals_sync.py --days 14 --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
os.chdir(API_DIR)

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resync planned_workouts for a historical date range from intervals.icu.",
    )
    parser.add_argument("--from", dest="from_date", type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument(
        "--days",
        type=int,
        help="Shortcut for --from/--to: the last N days up to and including today.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    return parser


def _confirm(from_date: date, to_date: date) -> bool:
    answer = input(f"\nResync planned_workouts for {from_date}..{to_date}? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _run(*, from_date: date, to_date: date) -> None:
    from app.db import session_scope
    from app.domain.intervals_sync import sync_intervals

    with session_scope() as session:
        result = sync_intervals(session, from_date=from_date, to_date=to_date)

    print(f"Synced {from_date}..{to_date}: {result.days_synced} planned_workouts rows upserted.")
    if result.failures:
        print(f"{len(result.failures)} row(s) failed and were skipped:")
        for failure in result.failures:
            print(f"  - {failure}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.days is not None and (args.from_date or args.to_date):
        print("Pass either --days or --from/--to, not both.")
        return 2

    if args.days is not None:
        to_date = datetime.now(UTC).date()
        from_date = to_date - timedelta(days=args.days - 1)
    elif args.from_date and args.to_date:
        from_date, to_date = args.from_date, args.to_date
    else:
        print("Must pass --days, or both --from and --to.")
        return 2

    if to_date < from_date:
        print("--to must be on or after --from.")
        return 2

    if not args.yes and not _confirm(from_date, to_date):
        print("\nCancelled.")
        return 0

    try:
        _run(from_date=from_date, to_date=to_date)
    except RuntimeError as exc:
        print("\nCould not load API settings.")
        print(f"Details: {exc}")
        return 2

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
