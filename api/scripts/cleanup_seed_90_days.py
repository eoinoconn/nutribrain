#!/usr/bin/env python3
"""Delete the rows added by a real run of ``seed_90_days.py``.

``seed_90_days.py`` was executed for real against the Neon dev database that
``api/tests/conftest.py``'s ``db_session`` fixture also points at. The test
harness only rolls back each test's own transaction; it does not undo data
committed by an external process using ``session_scope()``. This script
reverses that specific run by deleting rows that match the exact fingerprint
the seed script writes, without touching anything else:

* ``IntervalsCaloriesOut`` rows where ``fetched_at`` is exactly
  ``date`` at 06:00:00 UTC and ``source == sync`` — the precise pattern
  ``seed_90_days.py`` inserts, unlikely to coincide with a real sync.
* ``Meal`` rows whose ``logged_at`` time-of-day is exactly one of the four
  slots the seed script uses (08:00 breakfast, 13:00 lunch, 19:30 dinner,
  16:00 snack) with the matching ``meal_type``, within the seeded date range.
* ``Target`` rows at exactly ``start_date`` and ``mid_date`` (the two dates
  the seed script sets targets on).

Foods and templates are not covered by fingerprint matching here (the seed
script reused any food/template that already existed by exact name), so they
were removed separately by hand after confirming the test DB is expected to
hold no persistent Food/Template/Meal rows outside a test's own transaction
(see ``tests/test_harness.py``'s isolation tests).

Usage:
  uv run --project api python api/scripts/cleanup_seed_90_days.py --dry-run
  uv run --project api python api/scripts/cleanup_seed_90_days.py --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
os.chdir(API_DIR)

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# The exact values seed_90_days.py derived when it was run for real:
# today_local (Europe/Dublin) was 2026-07-28, days=90.
START_DATE = date(2026, 4, 30)
END_DATE = date(2026, 7, 28)
MID_DATE = date(2026, 6, 14)

# meal_type -> logged_at time-of-day (UTC) the seed script used for it.
MEAL_SLOTS: dict[str, time] = {
    "breakfast": time(8, 0),
    "lunch": time(13, 0),
    "dinner": time(19, 30),
    "snack": time(16, 0),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete rows added by the real seed_90_days.py run.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    return parser


def _confirm() -> bool:
    answer = input("\nDelete these rows? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _run(*, dry_run: bool) -> None:
    from sqlalchemy import select

    from app.db import IntervalsCaloriesOut, IntervalsSource, Meal, MealItem, Target, session_scope

    with session_scope() as session:
        # --- calories-out fingerprint match ---------------------------------
        cal_out_rows = session.scalars(
            select(IntervalsCaloriesOut).where(
                IntervalsCaloriesOut.date >= START_DATE,
                IntervalsCaloriesOut.date <= END_DATE,
                IntervalsCaloriesOut.source == IntervalsSource.sync,
            )
        ).all()
        cal_out_to_delete = [
            row
            for row in cal_out_rows
            if row.fetched_at == datetime.combine(row.date, time(6, 0), tzinfo=UTC)
        ]

        # --- meal fingerprint match ------------------------------------------
        meal_rows = session.scalars(
            select(Meal).where(
                Meal.local_date >= START_DATE,
                Meal.local_date <= END_DATE,
            )
        ).all()
        meals_to_delete = []
        for meal in meal_rows:
            meal_type = meal.meal_type.value if hasattr(meal.meal_type, "value") else meal.meal_type
            if MEAL_SLOTS.get(meal_type) == meal.logged_at.astimezone(UTC).time():
                meals_to_delete.append(meal)

        # --- target fingerprint match -----------------------------------------
        target_rows = session.scalars(
            select(Target).where(Target.effective_from.in_([START_DATE, MID_DATE]))
        ).all()

        print(f"IntervalsCaloriesOut rows matching seed fingerprint: {len(cal_out_to_delete)}")
        print(f"Meal rows matching seed fingerprint: {len(meals_to_delete)}")
        for meal in meals_to_delete[:5]:
            print(f"  - id={meal.id} meal_type={meal.meal_type} logged_at={meal.logged_at}")
        if len(meals_to_delete) > 5:
            print(f"  ... and {len(meals_to_delete) - 5} more")
        print(f"Target rows at start_date/mid_date: {len(target_rows)}")
        for target in target_rows:
            print(f"  - id={target.id} effective_from={target.effective_from}")

        if dry_run:
            print("\nDRY RUN — nothing deleted.")
            return

        if not meals_to_delete and not cal_out_to_delete and not target_rows:
            print("\nNothing to delete.")
            return

        meal_ids = [meal.id for meal in meals_to_delete]
        if meal_ids:
            item_count = (
                session.query(MealItem)
                .filter(MealItem.meal_id.in_(meal_ids))
                .delete(synchronize_session=False)
            )
            print(f"Deleted {item_count} meal_items.")
        for meal in meals_to_delete:
            session.delete(meal)
        for row in cal_out_to_delete:
            session.delete(row)
        for target in target_rows:
            session.delete(target)

        print(
            f"Deleted {len(meals_to_delete)} meals, {len(cal_out_to_delete)} calories-out rows, "
            f"{len(target_rows)} targets."
        )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.dry_run and not args.yes and not _confirm():
        print("\nCancelled.")
        return 0

    try:
        _run(dry_run=args.dry_run)
    except RuntimeError as exc:
        print("\nCould not load API settings.")
        print(f"Details: {exc}")
        return 2

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
