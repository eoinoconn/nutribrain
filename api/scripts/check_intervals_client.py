#!/usr/bin/env python3
"""Smoke-test intervals.icu per-activity fetch using api/.env settings.

Uses ``fetch_activities_detailed`` (EC-02) — the per-activity detail fetcher
that feeds ``planned_workouts``, and that ``get_effective_target`` now sums
for calories_out (EC-07). The old daily-sum ``fetch_activity_calories_by_day``
this script used to smoke-test has been retired.

Examples:
  uv run python scripts/check_intervals_client.py
  uv run python scripts/check_intervals_client.py --days 3
  uv run python scripts/check_intervals_client.py --from 2026-07-20 --to 2026-07-23
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Script lives in api/scripts/, so parent directory is api/.
API_DIR = Path(__file__).resolve().parents[1]

# Settings use env_file='.env'. Ensure this resolves to api/.env.
os.chdir(API_DIR)

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Run a live intervals.icu activity query using settings loaded from api/.env.")
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Look back this many days ending today (default: 7). Ignored if --from/--to is set.",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        help="Oldest date (YYYY-MM-DD). Must be provided with --to.",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        help="Newest date (YYYY-MM-DD). Must be provided with --from.",
    )
    return parser.parse_args()


def _resolve_window(args: argparse.Namespace) -> tuple[date, date]:
    if bool(args.from_date) != bool(args.to_date):
        raise SystemExit("Provide both --from and --to, or neither.")

    if args.from_date and args.to_date:
        oldest = date.fromisoformat(args.from_date)
        newest = date.fromisoformat(args.to_date)
    else:
        newest = datetime.now(UTC).date()
        oldest = newest - timedelta(days=args.days - 1)

    if newest < oldest:
        raise SystemExit("Invalid range: --to must be on or after --from.")

    return oldest, newest


def _masked_key(key: str) -> str:
    if len(key) <= 6:
        return "*" * len(key)
    return f"{key[:3]}...{key[-3:]}"


def main() -> int:
    args = _parse_args()
    oldest, newest = _resolve_window(args)

    try:
        from app.intervals.client import fetch_activities_detailed  # type: ignore[import-not-found]
        from app.settings import settings  # type: ignore[import-not-found]
    except RuntimeError as exc:
        print("Could not load API settings from api/.env.")
        print(f"Details: {exc}")
        return 2

    print("Intervals client smoke test")
    print(f"- athlete id: {settings.intervals_athlete_id}")
    print(f"- api key: {_masked_key(settings.intervals_api_key)}")
    print(f"- window: {oldest.isoformat()} -> {newest.isoformat()}")

    try:
        result = fetch_activities_detailed(oldest=oldest, newest=newest)
    except Exception as exc:
        print("- status: FAILED")
        print(f"- error: {type(exc).__name__}: {exc}")
        return 1

    print("- status: OK")
    print(f"- activities returned: {len(result)}")

    for activity in sorted(result, key=lambda a: a.start_date_local):
        print(
            f"  {activity.start_date_local} [{activity.external_id}] "
            f"{activity.sport_type}: {activity.calories} cal"
        )

    if result and all(activity.calories is None for activity in result):
        print("- warning: every activity returned None for calories")
        print("  This usually means activity rows in this range did not include a calories field.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
