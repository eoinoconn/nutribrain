#!/usr/bin/env python3
"""Seed ~90 days of plausible foods, templates, targets, meals, and
calories-out rows (T-102).

Unlike seed_dev_foods.py / seed_dev_meals.py (small, curated, single-day
presets meant for quick manual dev setup), this script exists to make Trends
and Calendar development meaningful, and to make the T-027 90-day
query-count/correctness assertion honest against something resembling real
usage: varied daily totals, some days over target, a mid-range target change,
and a calories-out row for every day.

Data is generated with a fixed random seed so re-running produces the same
*shape* of data (same relative pattern of meals/macros), even though the
absolute dates shift with "today".

Examples:
  uv run --project api python api/scripts/seed_90_days.py --dry-run --yes
  uv run --project api python api/scripts/seed_90_days.py --days 90 --yes
"""

from __future__ import annotations

import argparse
import os
import random
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


# A small, deliberately varied pool — enough to make Trends/Calendar charts
# look like a real eating pattern rather than one repeated meal.
FOODS: list[SeedFood] = [
    SeedFood("Rolled Oats", "40", "g", "150", "5.2", "27.0", "3.0", fiber_g="4.0", sodium_mg="2"),
    SeedFood("Greek Yogurt 2%", "170", "g", "146", "17.0", "6.0", "5.0", sodium_mg="65"),
    SeedFood("Banana", "118", "piece", "105", "1.3", "27.0", "0.3", fiber_g="3.1", sodium_mg="1"),
    SeedFood("Chicken Breast (Cooked)", "100", "g", "165", "31.0", "0.0", "3.6", sodium_mg="74"),
    SeedFood(
        "Cooked White Rice", "100", "g", "130", "2.4", "28.2", "0.3", fiber_g="0.4", sodium_mg="1"
    ),
    SeedFood(
        "Salmon Fillet (Cooked)",
        "100",
        "g",
        "208",
        "20.4",
        "0.0",
        "13.4",
        sat_fat_g="2.7",
        sodium_mg="59",
    ),
    SeedFood(
        "Mixed Green Salad", "100", "g", "20", "1.5", "3.5", "0.2", fiber_g="1.6", sodium_mg="15"
    ),
    SeedFood(
        "Olive Oil", "13.5", "ml", "119", "0.0", "0.0", "13.5", sat_fat_g="1.9", sodium_mg="0"
    ),
    SeedFood(
        "Whole Wheat Bread", "43", "g", "110", "4.0", "20.0", "1.5", fiber_g="2.0", sodium_mg="170"
    ),
    SeedFood(
        "Peanut Butter", "32", "g", "190", "8.0", "6.0", "16.0", fiber_g="2.0", sodium_mg="140"
    ),
    SeedFood("Egg", "50", "piece", "72", "6.3", "0.4", "4.8", sodium_mg="71"),
    SeedFood("Cottage Cheese", "113", "g", "98", "12.0", "4.0", "3.0", sodium_mg="360"),
    SeedFood("Almonds", "28", "g", "164", "6.0", "6.1", "14.2", fiber_g="3.5", sodium_mg="0"),
    SeedFood("Apple", "182", "piece", "95", "0.5", "25.0", "0.3", fiber_g="4.4", sodium_mg="2"),
]

# Templates reuse foods by name (resolved after foods are inserted).
TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "Standard Breakfast": [
        ("Rolled Oats", "40", "g"),
        ("Greek Yogurt 2%", "170", "g"),
        ("Banana", "1", "piece"),
    ],
    "Chicken Rice Bowl": [
        ("Chicken Breast (Cooked)", "150", "g"),
        ("Cooked White Rice", "150", "g"),
        ("Mixed Green Salad", "80", "g"),
        ("Olive Oil", "1", "serving"),
    ],
    "Salmon Dinner": [
        ("Salmon Fillet (Cooked)", "150", "g"),
        ("Cooked White Rice", "120", "g"),
        ("Mixed Green Salad", "100", "g"),
    ],
}

# Ad-hoc snacks with no food_id, to exercise that invariant in seeded data.
ADHOC_SNACKS: list[tuple[str, str, str, str, str]] = [
    ("Protein Bar (estimate)", "220", "20", "22", "8"),
    ("Coffee Shop Muffin (estimate)", "410", "6", "58", "17"),
    ("Restaurant Pasta (estimate)", "780", "24", "95", "30"),
]


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed ~90 days of foods, templates, targets, meals, and calories-out rows.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--days", type=int, default=90, help="How many most-recent days to populate (default: 90)."
    )
    parser.add_argument(
        "--tz",
        default="Europe/Dublin",
        help="IANA timezone for local dates (default: Europe/Dublin).",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed, for reproducible daily variation."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    return parser


def _confirm() -> bool:
    answer = input("\nContinue? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _plausible_calories_out(rng: random.Random, day_offset: int) -> int:
    # Rest days vs. training days: mostly moderate, occasional high-burn day.
    if day_offset % 7 in (2, 5):  # two "hard training" days per week
        return rng.randint(550, 800)
    return rng.randint(150, 400)


def _run(*, days: int, tz: str, seed: int, dry_run: bool) -> None:
    from sqlalchemy import select

    from app.db import (
        Food,
        IntervalsCaloriesOut,
        IntervalsSource,
        QuantityUnit,
        ServingUnit,
        Target,
        Template,
        session_scope,
    )
    from app.domain import MealItemSpec, log_meal, log_template
    from app.domain.dto import TemplateItemSpec
    from app.domain.errors import DomainError
    from app.domain.foods import add_food
    from app.domain.targets import set_target
    from app.domain.templates import create_template

    rng = random.Random(seed)
    today_local = datetime.now(ZoneInfo(tz)).date()
    start_date = today_local - timedelta(days=days - 1)

    if dry_run:
        print(f"\nDRY RUN — would seed {days} days ({start_date} .. {today_local}), tz={tz}")
        print(f"Foods: {len(FOODS)}, Templates: {len(TEMPLATES)}")
        print("Would set targets at day 0 (2000 kcal) and roughly day 45 (2200 kcal).")
        print(f"Would insert 1 calories_out row/day and 3-4 meals/day for {days} days.")
        return

    with session_scope() as session:
        # --- Foods: reuse if already present by exact name -----------------
        food_by_name: dict[str, int] = {}
        for f in FOODS:
            existing = session.scalar(select(Food).where(Food.name == f.name))
            if existing is not None:
                food_by_name[f.name] = existing.id
                continue
            result = add_food(
                session,
                name=f.name,
                serving_size=Decimal(f.serving_size),
                serving_unit=ServingUnit(f.serving_unit),
                calories=Decimal(f.calories),
                protein_g=Decimal(f.protein_g),
                carbs_g=Decimal(f.carbs_g),
                fat_g=Decimal(f.fat_g),
                fiber_g=_to_decimal(f.fiber_g),
                sat_fat_g=_to_decimal(f.sat_fat_g),
                sodium_mg=_to_decimal(f.sodium_mg),
                density_g_per_ml=_to_decimal(f.density_g_per_ml),
                force=True,
            )
            food_by_name[f.name] = result.food.id
        print(f"Foods ready: {len(food_by_name)}")

        # --- Templates: reuse if already present by exact name --------------
        template_by_name: dict[str, int] = {}
        for name, items in TEMPLATES.items():
            existing_template = session.scalar(
                select(Template).where(Template.name == name, Template.deleted_at.is_(None))
            )
            if existing_template is not None:
                template_by_name[name] = existing_template.id
                continue
            specs = [
                TemplateItemSpec(
                    food_id=food_by_name[item_name],
                    name=item_name,
                    quantity=Decimal(qty),
                    quantity_unit=QuantityUnit(unit),
                )
                for item_name, qty, unit in items
            ]
            response = create_template(session, name=name, items=specs)
            template_by_name[name] = response.id
        print(f"Templates ready: {len(template_by_name)}")

        # --- Targets: one from day 0, one change partway through ------------
        if session.scalar(select(Target).where(Target.effective_from == start_date)) is None:
            set_target(
                session,
                base_calories=2000,
                protein_g=150,
                carbs_g=220,
                fat_g=70,
                effective_from=start_date,
            )
        mid_date = start_date + timedelta(days=45)
        mid_target_exists = (
            session.scalar(select(Target).where(Target.effective_from == mid_date)) is not None
        )
        if days > 45 and not mid_target_exists:
            set_target(
                session,
                base_calories=2200,
                protein_g=160,
                carbs_g=230,
                fat_g=75,
                effective_from=mid_date,
            )
        print("Targets set.")

        # --- Per-day calories-out + meals ------------------------------------
        template_names = list(TEMPLATES.keys())
        meals_created = 0
        cal_out_created = 0

        for day_offset in range(days):
            day = start_date + timedelta(days=day_offset)

            if session.get(IntervalsCaloriesOut, day) is None:
                cal_out = IntervalsCaloriesOut(
                    date=day,
                    calories_out=_plausible_calories_out(rng, day_offset),
                    fetched_at=datetime(day.year, day.month, day.day, 6, 0, tzinfo=UTC),
                    source=IntervalsSource.sync,
                )
                session.add(cal_out)
                cal_out_created += 1

            # Breakfast: template, most days.
            if rng.random() < 0.9:
                logged_at = datetime(day.year, day.month, day.day, 8, 0, tzinfo=UTC)
                try:
                    log_template(
                        session,
                        template_id=template_by_name["Standard Breakfast"],
                        logged_at=logged_at,
                        local_tz=tz,
                        meal_type="breakfast",
                    )
                    meals_created += 1
                except DomainError:
                    pass

            # Lunch: alternate between two templates.
            lunch_template = template_names[1] if day_offset % 2 == 0 else template_names[2]
            logged_at = datetime(day.year, day.month, day.day, 13, 0, tzinfo=UTC)
            scale = Decimal(str(round(rng.uniform(0.85, 1.15), 2)))
            try:
                log_template(
                    session,
                    template_id=template_by_name[lunch_template],
                    logged_at=logged_at,
                    local_tz=tz,
                    meal_type="lunch",
                    quantity_scale=scale,
                )
                meals_created += 1
            except DomainError:
                pass

            # Dinner: food-backed ad-hoc log_meal call, varied quantity.
            logged_at = datetime(day.year, day.month, day.day, 19, 30, tzinfo=UTC)
            dinner_food = rng.choice(["Salmon Fillet (Cooked)", "Chicken Breast (Cooked)"])
            try:
                log_meal(
                    session,
                    items=[
                        MealItemSpec(
                            name=dinner_food,
                            food_id=food_by_name[dinner_food],
                            quantity=Decimal(str(rng.randint(120, 200))),
                            quantity_unit=QuantityUnit.g,
                        ),
                        MealItemSpec(
                            name="Cooked White Rice",
                            food_id=food_by_name["Cooked White Rice"],
                            quantity=Decimal(str(rng.randint(100, 180))),
                            quantity_unit=QuantityUnit.g,
                        ),
                    ],
                    logged_at=logged_at,
                    local_tz=tz,
                    meal_type="dinner",
                )
                meals_created += 1
            except DomainError:
                pass

            # Snack: ~40% of days, ad-hoc estimate (exercises the no-food_id path).
            if rng.random() < 0.4:
                snack = rng.choice(ADHOC_SNACKS)
                name, calories, protein_g, carbs_g, fat_g = snack
                logged_at = datetime(day.year, day.month, day.day, 16, 0, tzinfo=UTC)
                try:
                    log_meal(
                        session,
                        items=[
                            MealItemSpec(
                                name=name,
                                food_id=None,
                                quantity=Decimal("1"),
                                quantity_unit=QuantityUnit.serving,
                                calories=Decimal(calories),
                                protein_g=Decimal(protein_g),
                                carbs_g=Decimal(carbs_g),
                                fat_g=Decimal(fat_g),
                            )
                        ],
                        logged_at=logged_at,
                        local_tz=tz,
                        meal_type="snack",
                    )
                    meals_created += 1
                except DomainError:
                    pass

        print(f"Calories-out rows: {cal_out_created}")
        print(f"Meals created: {meals_created}")


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

    print(f"\nWill seed {args.days} days of foods/templates/targets/meals/calories-out.")
    print(f"Timezone: {args.tz}  Random seed: {args.seed}")
    if not args.dry_run and not args.yes and not _confirm():
        print("\nCancelled.")
        return 0

    try:
        _run(days=args.days, tz=args.tz, seed=args.seed, dry_run=args.dry_run)
    except RuntimeError as exc:
        print("\nCould not load API settings.")
        print("Create api/.env first (DATABASE_URL, APP_TOKEN, and intervals vars).")
        print(f"Details: {exc}")
        return 2

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
