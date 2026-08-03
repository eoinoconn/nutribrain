#!/usr/bin/env python3
"""Delete all domain data rows from the database ``DATABASE_URL`` points at.

Meant for wiping a dev/test Neon branch (or the local Docker Postgres) back
to an empty-but-migrated state, e.g. after ad-hoc manual testing or a
``seed_90_days.py`` run has left the shared dev DB with rows that break
count-based test assertions (see ``tests/test_harness.py``'s isolation
tests, which assume the DB starts empty).

This clears, in FK-safe (child-before-parent) order:
  meal_items, meals, template_items, templates, targets,
  intervals_calories_out, planned_workouts, foods, intervals_sync_status.

It does NOT touch ``app_settings`` (account timezone) or ``mcp_oauth_kv``
(OAuth proxy state) by default, since those are config/auth state rather
than nutrition/fitness data, and wiping ``mcp_oauth_kv`` would force every
connected MCP client to re-authenticate. Pass ``--include-settings`` to
clear those too.

There is no reliable way for this script to tell a dev Neon branch from a
production one by URL shape alone, so it always prints the target host/db
name and requires explicit confirmation (or ``--yes`` for scripted use).

Usage:
  uv run --project api python api/scripts/clear_dev_db.py --dry-run
  uv run --project api python api/scripts/clear_dev_db.py --yes
  uv run --project api python api/scripts/clear_dev_db.py --yes --include-settings
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

API_DIR = Path(__file__).resolve().parents[1]
os.chdir(API_DIR)

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete all domain data from the DATABASE_URL-configured database.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report row counts without deleting."
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    parser.add_argument(
        "--include-settings",
        action="store_true",
        help="Also clear app_settings and mcp_oauth_kv (resets timezone, logs out MCP clients).",
    )
    return parser


def _confirm(target: str) -> bool:
    answer = input(f"\nDelete ALL data on {target}? Type the host name to confirm: ").strip()
    return answer == target


def _run(*, dry_run: bool, include_settings: bool, yes: bool) -> None:
    from sqlalchemy import func, select

    from app.db import (
        AppSettings,
        Food,
        IntervalsCaloriesOut,
        IntervalsSyncStatus,
        McpOAuthKV,
        Meal,
        MealItem,
        PlannedWorkout,
        Target,
        Template,
        TemplateItem,
        session_scope,
    )
    from app.settings import settings

    # Normalize the SQLAlchemy "+psycopg" driver suffix so urlsplit sees a
    # plain scheme, then strip credentials so we never print a password.
    plain_url = settings.database_url.replace("postgresql+psycopg", "postgresql", 1)
    host = urlsplit(plain_url).netloc.rsplit("@", 1)[-1]

    models = [
        MealItem,
        Meal,
        TemplateItem,
        Template,
        Target,
        IntervalsCaloriesOut,
        PlannedWorkout,
        Food,
        IntervalsSyncStatus,
    ]
    if include_settings:
        models += [AppSettings, McpOAuthKV]

    with session_scope() as session:
        counts = {
            model.__tablename__: session.execute(
                select(func.count()).select_from(model)
            ).scalar_one()
            for model in models
        }

        print(f"Target database: {host}")
        for name, count in counts.items():
            print(f"  {name}: {count}")

        if dry_run:
            print("\nDRY RUN — nothing deleted.")
            return

        if not any(counts.values()):
            print("\nNothing to delete.")
            return

        if not yes and not _confirm(host):
            print("\nCancelled.")
            return

        for model in models:
            session.query(model).delete(synchronize_session=False)

        print(f"\nDeleted rows from {len(models)} tables.")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        _run(dry_run=args.dry_run, include_settings=args.include_settings, yes=args.yes)
    except RuntimeError as exc:
        print("\nCould not load API settings.")
        print(f"Details: {exc}")
        return 2

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
