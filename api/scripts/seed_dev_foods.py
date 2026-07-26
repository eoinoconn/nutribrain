#!/usr/bin/env python3
"""Seed the development database with sample foods.

This script is intentionally friendly for day-to-day dev use:
- shows available presets
- confirms before writing
- skips duplicates by default
- supports dry-run mode

Examples:
    uv run --project api python api/scripts/seed_dev_foods.py
    uv run --project api python api/scripts/seed_dev_foods.py --preset breakfast
    uv run --project api python api/scripts/seed_dev_foods.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

# Script now lives in api/scripts/, so its parent directory is api/.
API_DIR = Path(__file__).resolve().parents[1]

# Settings use env_file='.env'. Make sure that resolves to api/.env
# even when this script is launched from repository root.
os.chdir(API_DIR)

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


@dataclass(frozen=True, slots=True)
class SeedFood:
    name: str
    serving_size: str
    serving_unit: str
    calories: str
    protein_g: str
    carbs_g: str
    fat_g: str
    fiber_g: str | None = None
    sat_fat_g: str | None = None
    sodium_mg: str | None = None
    density_g_per_ml: str | None = None


PRESETS: dict[str, list[SeedFood]] = {
    "starter": [
        SeedFood(
            name="Rolled Oats",
            serving_size="40",
            serving_unit="g",
            calories="150",
            protein_g="5.2",
            carbs_g="27.0",
            fat_g="3.0",
            fiber_g="4.0",
            sodium_mg="2",
        ),
        SeedFood(
            name="Greek Yogurt 2%",
            serving_size="170",
            serving_unit="g",
            calories="146",
            protein_g="17.0",
            carbs_g="6.0",
            fat_g="5.0",
            sodium_mg="65",
        ),
        SeedFood(
            name="Banana",
            serving_size="118",
            serving_unit="piece",
            calories="105",
            protein_g="1.3",
            carbs_g="27.0",
            fat_g="0.3",
            fiber_g="3.1",
            sodium_mg="1",
        ),
        SeedFood(
            name="Chicken Breast (Cooked)",
            serving_size="100",
            serving_unit="g",
            calories="165",
            protein_g="31.0",
            carbs_g="0.0",
            fat_g="3.6",
            sodium_mg="74",
        ),
        SeedFood(
            name="Cooked White Rice",
            serving_size="100",
            serving_unit="g",
            calories="130",
            protein_g="2.4",
            carbs_g="28.2",
            fat_g="0.3",
            fiber_g="0.4",
            sodium_mg="1",
        ),
        SeedFood(
            name="Whole Milk",
            serving_size="100",
            serving_unit="ml",
            calories="61",
            protein_g="3.2",
            carbs_g="4.8",
            fat_g="3.3",
            sat_fat_g="1.9",
            sodium_mg="43",
            density_g_per_ml="1.03",
        ),
    ],
    "breakfast": [
        SeedFood(
            name="Whole Egg",
            serving_size="1",
            serving_unit="piece",
            calories="72",
            protein_g="6.3",
            carbs_g="0.4",
            fat_g="4.8",
            sodium_mg="71",
        ),
        SeedFood(
            name="Sourdough Bread Slice",
            serving_size="38",
            serving_unit="piece",
            calories="100",
            protein_g="4.0",
            carbs_g="19.0",
            fat_g="1.0",
            fiber_g="1.0",
            sodium_mg="190",
        ),
        SeedFood(
            name="Peanut Butter",
            serving_size="32",
            serving_unit="g",
            calories="188",
            protein_g="8.0",
            carbs_g="6.0",
            fat_g="16.0",
            fiber_g="2.0",
            sodium_mg="136",
        ),
    ],
}


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed sample foods into your dev database.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        default="starter",
        help="Which sample set to insert.",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="Show presets and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without writing to the database.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass duplicate-name protection in add_food.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    return parser


def _print_presets() -> None:
    print("Available presets:")
    for name, foods in PRESETS.items():
        print(f"  - {name}: {len(foods)} foods")


def _print_plan(preset: str, foods: list[SeedFood], dry_run: bool, force: bool) -> None:
    mode = "DRY RUN" if dry_run else "WRITE"
    print(f"\nSeed mode: {mode}")
    print(f"Preset: {preset}")
    print(f"Duplicate policy: {'force insert' if force else 'skip duplicates'}")
    print("\nFoods to process:")
    for idx, food in enumerate(foods, start=1):
        print(
            f"  {idx:>2}. {food.name}"
            f" ({food.serving_size} {food.serving_unit}, {food.calories} kcal)"
        )


def _confirm() -> bool:
    answer = input("\nContinue? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _seed_foods(foods: list[SeedFood], *, force: bool, dry_run: bool) -> tuple[int, int]:
    if dry_run:
        return (0, 0)

    try:
        from app.db import ServingUnit, session_scope  # type: ignore[import-not-found]
        from app.domain import FoodDuplicateError, add_food  # type: ignore[import-not-found]
    except RuntimeError as exc:
        print("\nCould not load API settings.")
        print("Create api/.env first (DATABASE_URL, APP_TOKEN, and intervals vars).")
        print(f"Details: {exc}")
        raise SystemExit(2) from exc

    created = 0
    skipped_duplicates = 0

    with session_scope() as session:
        for food in foods:
            try:
                result = add_food(
                    session,
                    name=food.name,
                    serving_size=Decimal(food.serving_size),
                    serving_unit=ServingUnit(food.serving_unit),
                    calories=Decimal(food.calories),
                    protein_g=Decimal(food.protein_g),
                    carbs_g=Decimal(food.carbs_g),
                    fat_g=Decimal(food.fat_g),
                    fiber_g=_to_decimal(food.fiber_g),
                    sat_fat_g=_to_decimal(food.sat_fat_g),
                    sodium_mg=_to_decimal(food.sodium_mg),
                    density_g_per_ml=_to_decimal(food.density_g_per_ml),
                    force=force,
                )
            except FoodDuplicateError:
                skipped_duplicates += 1
                print(f"  [skip] {food.name} (duplicate)")
                continue

            created += 1
            print(f"  [ok] Added #{result.food.id}: {result.food.name}")

    return (created, skipped_duplicates)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.list_presets:
        _print_presets()
        return 0

    foods = PRESETS[args.preset]
    _print_plan(args.preset, foods, args.dry_run, args.force)

    if not args.yes and not _confirm():
        print("\nCancelled.")
        return 0

    created, skipped_duplicates = _seed_foods(foods, force=args.force, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\nDry run complete. {len(foods)} foods would be processed.")
        return 0

    print("\nDone.")
    print(f"Created: {created}")
    print(f"Skipped duplicates: {skipped_duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
