#!/usr/bin/env python3
"""Seed the development database with sample meals.

This script is designed for fast dev setup:
- preset meal plans
- optional dry-run preview
- confirmation prompt before writes
- ability to repeat the plan over multiple recent days

Examples:
  uv run --project api python api/scripts/seed_dev_meals.py --list-presets
  uv run --project api python api/scripts/seed_dev_meals.py --dry-run --yes
  uv run --project api python api/scripts/seed_dev_meals.py --days 3 --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

# Script lives in api/scripts/, so parent directory is api/.
API_DIR = Path(__file__).resolve().parents[1]

# Settings use env_file='.env'. Ensure this resolves to api/.env
os.chdir(API_DIR)

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


@dataclass(frozen=True, slots=True)
class SeedMealItem:
    name: str
    quantity: str
    quantity_unit: str
    calories: str
    protein_g: str
    carbs_g: str
    fat_g: str
    fiber_g: str | None = None
    sat_fat_g: str | None = None
    sodium_mg: str | None = None


@dataclass(frozen=True, slots=True)
class SeedMeal:
    title: str
    meal_type: str
    hour: int
    minute: int
    notes: str
    items: list[SeedMealItem]


PRESETS: dict[str, list[SeedMeal]] = {
    "starter": [
        SeedMeal(
            title="Protein Oat Bowl",
            meal_type="breakfast",
            hour=8,
            minute=0,
            notes="Dev seed breakfast",
            items=[
                SeedMealItem(
                    name="Oats Bowl",
                    quantity="1",
                    quantity_unit="serving",
                    calories="420",
                    protein_g="28",
                    carbs_g="54",
                    fat_g="11",
                    fiber_g="7",
                    sodium_mg="180",
                ),
            ],
        ),
        SeedMeal(
            title="Chicken Rice Plate",
            meal_type="lunch",
            hour=13,
            minute=0,
            notes="Dev seed lunch",
            items=[
                SeedMealItem(
                    name="Chicken and Rice",
                    quantity="1",
                    quantity_unit="serving",
                    calories="610",
                    protein_g="46",
                    carbs_g="68",
                    fat_g="16",
                    fiber_g="4",
                    sodium_mg="540",
                ),
                SeedMealItem(
                    name="Olive Oil Drizzle",
                    quantity="1",
                    quantity_unit="tbsp",
                    calories="119",
                    protein_g="0",
                    carbs_g="0",
                    fat_g="13.5",
                    sat_fat_g="1.9",
                    sodium_mg="0",
                ),
            ],
        ),
        SeedMeal(
            title="Yogurt Snack",
            meal_type="snack",
            hour=16,
            minute=30,
            notes="Dev seed snack",
            items=[
                SeedMealItem(
                    name="Yogurt Cup",
                    quantity="1",
                    quantity_unit="serving",
                    calories="210",
                    protein_g="16",
                    carbs_g="20",
                    fat_g="7",
                    sodium_mg="120",
                ),
            ],
        ),
        SeedMeal(
            title="Salmon and Potatoes",
            meal_type="dinner",
            hour=19,
            minute=30,
            notes="Dev seed dinner",
            items=[
                SeedMealItem(
                    name="Salmon Plate",
                    quantity="1",
                    quantity_unit="serving",
                    calories="700",
                    protein_g="48",
                    carbs_g="52",
                    fat_g="31",
                    fiber_g="6",
                    sat_fat_g="7",
                    sodium_mg="640",
                ),
            ],
        ),
    ],
    "light_day": [
        SeedMeal(
            title="Egg Toast",
            meal_type="breakfast",
            hour=8,
            minute=15,
            notes="Dev seed light breakfast",
            items=[
                SeedMealItem(
                    name="Egg Toast",
                    quantity="1",
                    quantity_unit="serving",
                    calories="330",
                    protein_g="18",
                    carbs_g="26",
                    fat_g="17",
                    fiber_g="3",
                    sodium_mg="370",
                ),
            ],
        ),
        SeedMeal(
            title="Turkey Wrap",
            meal_type="lunch",
            hour=12,
            minute=45,
            notes="Dev seed light lunch",
            items=[
                SeedMealItem(
                    name="Turkey Wrap",
                    quantity="1",
                    quantity_unit="serving",
                    calories="520",
                    protein_g="35",
                    carbs_g="44",
                    fat_g="21",
                    fiber_g="6",
                    sodium_mg="760",
                ),
            ],
        ),
        SeedMeal(
            title="Steak Salad",
            meal_type="dinner",
            hour=19,
            minute=0,
            notes="Dev seed light dinner",
            items=[
                SeedMealItem(
                    name="Steak Salad",
                    quantity="1",
                    quantity_unit="serving",
                    calories="610",
                    protein_g="42",
                    carbs_g="28",
                    fat_g="34",
                    fiber_g="9",
                    sodium_mg="590",
                ),
            ],
        ),
    ],
}


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed sample meals into your dev database.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        default="starter",
        help="Which sample meal plan to use.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Repeat this meal plan for N most recent days (default: 1).",
    )
    parser.add_argument(
        "--tz",
        default="Europe/Dublin",
        help="IANA timezone for meal timestamps (default: Europe/Dublin).",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="Show available presets and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without writing to the database.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    return parser


def _print_presets() -> None:
    print("Available meal presets:")
    for name, meals in PRESETS.items():
        print(f"  - {name}: {len(meals)} meals")


def _render_local_logged_at(meal: SeedMeal, tz: str, days_ago: int) -> datetime:
    now_local = datetime.now(ZoneInfo(tz))
    local_dt = now_local.replace(hour=meal.hour, minute=meal.minute, second=0, microsecond=0)
    return local_dt - timedelta(days=days_ago)


def _print_plan(preset: str, meals: list[SeedMeal], *, days: int, tz: str, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "WRITE"
    total_meals = len(meals) * days
    print(f"\nSeed mode: {mode}")
    print(f"Preset: {preset}")
    print(f"Timezone: {tz}")
    print(f"Days: {days}")
    print(f"Total meals to process: {total_meals}")
    print("\nMeals to process:")
    for day_idx in range(days):
        for meal in meals:
            local_dt = _render_local_logged_at(meal, tz, day_idx)
            when = local_dt.strftime("%Y-%m-%d %H:%M")
            print(
                f"  - {when} | {meal.meal_type:9s} | {meal.title}"
                f" ({len(meal.items)} item{'s' if len(meal.items) != 1 else ''})"
            )


def _confirm() -> bool:
    answer = input("\nContinue? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _seed_meals(
    meals: list[SeedMeal],
    *,
    days: int,
    tz: str,
    dry_run: bool,
) -> int:
    if dry_run:
        return 0

    try:
        from app.db import QuantityUnit, session_scope  # type: ignore[import-not-found]
        from app.domain import MealItemSpec, log_meal  # type: ignore[import-not-found]
        from app.domain.errors import DomainError  # type: ignore[import-not-found]
    except RuntimeError as exc:
        print("\nCould not load API settings.")
        print("Create api/.env first (DATABASE_URL, APP_TOKEN, and intervals vars).")
        print(f"Details: {exc}")
        raise SystemExit(2) from exc

    created = 0

    with session_scope() as session:
        for day_idx in range(days):
            for meal in meals:
                local_logged_at = _render_local_logged_at(meal, tz, day_idx)
                logged_at_utc = local_logged_at.astimezone(UTC)

                specs = [
                    MealItemSpec(
                        name=item.name,
                        quantity=Decimal(item.quantity),
                        quantity_unit=QuantityUnit(item.quantity_unit),
                        calories=Decimal(item.calories),
                        protein_g=Decimal(item.protein_g),
                        carbs_g=Decimal(item.carbs_g),
                        fat_g=Decimal(item.fat_g),
                        fiber_g=_to_decimal(item.fiber_g),
                        sat_fat_g=_to_decimal(item.sat_fat_g),
                        sodium_mg=_to_decimal(item.sodium_mg),
                    )
                    for item in meal.items
                ]

                try:
                    response = log_meal(
                        session,
                        items=specs,
                        logged_at=logged_at_utc,
                        local_tz=tz,
                        meal_type=meal.meal_type,
                        notes=meal.notes,
                    )
                except DomainError as exc:
                    print(f"  [skip] {meal.title} ({exc.error}: {exc.message})")
                    continue

                created += 1
                print(
                    f"  [ok] Meal #{response.id} {response.meal_type.value}"
                    f" {response.local_date}: {meal.title}"
                )

    return created


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.days < 1:
        print("--days must be >= 1")
        return 2

    try:
        _ = ZoneInfo(args.tz)
    except Exception:
        print(f"Invalid timezone: {args.tz}")
        return 2

    if args.list_presets:
        _print_presets()
        return 0

    meals = PRESETS[args.preset]
    _print_plan(args.preset, meals, days=args.days, tz=args.tz, dry_run=args.dry_run)

    if not args.yes and not _confirm():
        print("\nCancelled.")
        return 0

    created = _seed_meals(meals, days=args.days, tz=args.tz, dry_run=args.dry_run)

    if args.dry_run:
        total = len(meals) * args.days
        print(f"\nDry run complete. {total} meals would be processed.")
        return 0

    print("\nDone.")
    print(f"Created meals: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
