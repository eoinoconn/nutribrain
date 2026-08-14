"""Tests for day and range aggregation (T-027).

Validates:
- get_day returns meals grouped by type with correct totals and target delta
- get_range returns per-period totals with adherence flags
- 90-day range over seeded data returns correct totals in bounded queries
- Read-time computation: no snapshotted macros, food edits propagate
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db import (
    Meal,
    MealItem,
    MealItemSource,
    MealType,
    PlannedWorkout,
    PlannedWorkoutSource,
    PlannedWorkoutStatus,
    QuantityUnit,
)
from app.domain.day_aggregation import get_day, get_range


class TestGetDay:
    """Tests for the get_day domain function."""

    def test_empty_day(self, db_session: Session, make_target):
        """A day with no meals returns zero totals."""
        make_target(effective_from=date(2026, 1, 1))
        result = get_day(db_session, day=date(2026, 7, 26))

        assert result.date == date(2026, 7, 26)
        assert result.day_totals.calories == Decimal("0")
        assert result.day_totals.protein_g == Decimal("0")
        assert result.meals == {}

    def test_single_meal_with_food_backed_items(
        self, db_session: Session, make_food, make_meal, make_meal_item, make_target
    ):
        """Food-backed items compute macros at read time."""
        food = make_food(
            name="Rice",
            serving_size=Decimal("100"),
            calories=Decimal("130"),
            protein_g=Decimal("2.7"),
            carbs_g=Decimal("28"),
            fat_g=Decimal("0.3"),
        )
        make_target(effective_from=date(2026, 1, 1), base_calories=2200)

        meal = make_meal(
            logged_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 26),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal.id, food=food, quantity=Decimal("200"), name="Rice")

        result = get_day(db_session, day=date(2026, 7, 26))

        assert result.date == date(2026, 7, 26)
        assert MealType.lunch in result.meals
        lunch_meals = result.meals[MealType.lunch]
        assert len(lunch_meals) == 1
        assert len(lunch_meals[0].items) == 1

        # 200g of food with 130 cal per 100g = 260 cal
        assert result.day_totals.calories == Decimal("260")
        assert result.day_totals.protein_g == Decimal("5.4")

    def test_multiple_meal_types_grouped(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        """Meals are grouped by meal_type in the response."""
        food = make_food(calories=Decimal("100"), protein_g=Decimal("10"))

        breakfast = make_meal(
            logged_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
            local_date=date(2026, 7, 26),
            meal_type=MealType.breakfast,
        )
        make_meal_item(meal_id=breakfast.id, food=food, name="Eggs")

        lunch = make_meal(
            logged_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 26),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=lunch.id, food=food, name="Chicken")

        result = get_day(db_session, day=date(2026, 7, 26))

        assert MealType.breakfast in result.meals
        assert MealType.lunch in result.meals
        assert len(result.meals[MealType.breakfast]) == 1
        assert len(result.meals[MealType.lunch]) == 1

    def test_effective_target_with_calories_out(
        self, db_session: Session, make_target, make_meal, make_meal_item, make_food
    ):
        """Effective target includes base + calories_out."""
        # A distinct future date, not 2026-07-26 like the rest of this file's
        # fixtures — avoids collisions with any pre-existing meals/targets for
        # that date in a long-lived shared database.
        day = date(2031, 7, 26)

        make_target(
            effective_from=date(2031, 1, 1),
            base_calories=2000,
            protein_g=150,
            carbs_g=220,
            fat_g=70,
        )

        # Add calories_out for the day via a completed planned_workout (EC-07:
        # get_day derives calories_out from planned_workouts, not a synced
        # intervals_calories_out row).
        completed_workout = PlannedWorkout(
            external_id="w-500",
            source=PlannedWorkoutSource.intervals_completed,
            local_date=day,
            start_at=datetime(2031, 7, 26, 6, 0, tzinfo=UTC),
            duration_minutes=45,
            sport_type="Ride",
            icu_joules=None,
            estimated_calories=None,
            actual_calories=500,
            status=PlannedWorkoutStatus.completed,
            fetched_at=datetime(2031, 7, 26, 6, 0, tzinfo=UTC),
        )
        db_session.add(completed_workout)
        db_session.flush()

        food = make_food(calories=Decimal("300"))
        meal = make_meal(
            logged_at=datetime(2031, 7, 26, 12, 0, tzinfo=UTC),
            local_date=day,
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal.id, food=food, name="Lunch item")

        result = get_day(db_session, day=day)

        assert result.effective_target is not None
        assert result.effective_target.base_calories == 2000
        assert result.effective_target.calories_out == 500
        assert result.effective_target.effective_calories == 2500

        # Delta: 300 - 2500 = -2200
        assert result.delta_vs_target is not None
        assert result.delta_vs_target.calories == Decimal("-2200")

    def test_no_target_returns_none_delta(self, db_session: Session):
        """If no target is set, effective_target and delta are None."""
        result = get_day(db_session, day=date(2026, 7, 26))

        assert result.effective_target is None
        assert result.delta_vs_target is None

    def test_ad_hoc_items_use_stored_macros(self, db_session: Session, make_meal, make_meal_item):
        """Ad-hoc items (no food_id) return their stored macros."""
        meal = make_meal(
            logged_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 26),
            meal_type=MealType.lunch,
        )
        make_meal_item(
            meal_id=meal.id,
            food_id=None,
            name="Estimate",
            calories=Decimal("400"),
            protein_g=Decimal("20"),
            carbs_g=Decimal("50"),
            fat_g=Decimal("15"),
        )

        result = get_day(db_session, day=date(2026, 7, 26))

        assert result.day_totals.calories == Decimal("400")
        assert result.day_totals.protein_g == Decimal("20")

    def test_food_edit_propagates_to_read(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ):
        """Editing a food's macros propagates to get_day (read-time computation)."""
        food = make_food(calories=Decimal("100"), protein_g=Decimal("10"))
        meal = make_meal(
            logged_at=datetime(2026, 7, 26, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 26),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal.id, food=food, name="Test")

        # Initially 100 cal
        result = get_day(db_session, day=date(2026, 7, 26))
        assert result.day_totals.calories == Decimal("100")

        # Edit food
        food.calories = Decimal("200")
        db_session.flush()

        # Read again — should reflect updated food
        result = get_day(db_session, day=date(2026, 7, 26))
        assert result.day_totals.calories == Decimal("200")


class TestGetRange:
    """Tests for the get_range domain function."""

    def test_empty_range(self, db_session: Session):
        """An empty range returns zero totals for each day."""
        result = get_range(
            db_session,
            from_date=date(2026, 7, 20),
            to_date=date(2026, 7, 22),
            granularity="day",
        )

        assert result.from_date == date(2026, 7, 20)
        assert result.to_date == date(2026, 7, 22)
        assert len(result.periods) == 3
        for period in result.periods:
            assert period.totals.calories == Decimal("0")

    def test_daily_granularity_with_meals(
        self, db_session: Session, make_food, make_meal, make_meal_item, make_target
    ):
        """Daily granularity returns per-day totals and adherence."""
        food = make_food(calories=Decimal("500"), protein_g=Decimal("30"))
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)

        # Day 1: 500 cal (within target)
        meal1 = make_meal(
            logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 20),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal1.id, food=food, name="Food")

        # Day 2: 1000 cal (within target)
        meal2 = make_meal(
            logged_at=datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 21),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal2.id, food=food, name="Food", quantity=Decimal("200"))

        result = get_range(
            db_session,
            from_date=date(2026, 7, 20),
            to_date=date(2026, 7, 21),
            granularity="day",
        )

        assert len(result.periods) == 2
        assert result.periods[0].totals.calories == Decimal("500")
        assert result.periods[0].adherence is True  # 500 <= 2000
        assert result.periods[1].totals.calories == Decimal("1000")
        assert result.periods[1].adherence is True  # 1000 <= 2000

    def test_weekly_granularity(
        self, db_session: Session, make_food, make_meal, make_meal_item, make_target
    ):
        """Weekly granularity sums daily totals into week periods."""
        food = make_food(calories=Decimal("100"))
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)

        # Create meals across 2 weeks (Mon 2026-07-06 to Sun 2026-07-19)
        for day_offset in range(14):
            day = date(2026, 7, 6) + timedelta(days=day_offset)
            meal = make_meal(
                logged_at=datetime(2026, 7, 6 + day_offset, 12, 0, tzinfo=UTC),
                local_date=day,
                meal_type=MealType.lunch,
            )
            make_meal_item(meal_id=meal.id, food=food, name="Daily food")

        result = get_range(
            db_session,
            from_date=date(2026, 7, 6),
            to_date=date(2026, 7, 19),
            granularity="week",
        )

        assert len(result.periods) == 2
        # Each week: 7 days * 100 cal = 700 cal
        assert result.periods[0].totals.calories == Decimal("700")
        assert result.periods[1].totals.calories == Decimal("700")

    def test_adherence_flag_over_target(
        self, db_session: Session, make_food, make_meal, make_meal_item, make_target
    ):
        """Adherence is False when calories exceed effective target."""
        food = make_food(calories=Decimal("3000"))
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)

        meal = make_meal(
            logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
            local_date=date(2026, 7, 20),
            meal_type=MealType.lunch,
        )
        make_meal_item(meal_id=meal.id, food=food, name="Big meal")

        result = get_range(
            db_session,
            from_date=date(2026, 7, 20),
            to_date=date(2026, 7, 20),
            granularity="day",
        )

        assert result.periods[0].adherence is False  # 3000 > 2000

    def test_invalid_granularity_raises(self, db_session: Session):
        """Invalid granularity raises ValueError."""
        with pytest.raises(ValueError, match="granularity must be"):
            get_range(
                db_session,
                from_date=date(2026, 7, 20),
                to_date=date(2026, 7, 20),
                granularity="month",
            )

    def test_90_day_range_bounded_queries(self, db_session: Session, make_food, make_target):
        """A 90-day range over seeded data returns correct totals.

        This is the acceptance test from the issue: 90 days of data, correct
        totals, bounded number of queries (no N+1).
        """
        food = make_food(
            name="Daily Staple",
            calories=Decimal("500"),
            protein_g=Decimal("25"),
            carbs_g=Decimal("60"),
            fat_g=Decimal("10"),
        )
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)

        start = date(2026, 4, 1)
        end = date(2026, 6, 29)  # 90 days

        # Seed 90 days of meals — one meal per day with one item
        for day_offset in range(90):
            day = start + timedelta(days=day_offset)
            logged_at = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
            meal = Meal(
                logged_at=logged_at,
                local_tz="Europe/Dublin",
                local_date=day,
                meal_type=MealType.lunch,
            )
            db_session.add(meal)
            db_session.flush()

            item = MealItem(
                meal_id=meal.id,
                food_id=food.id,
                name="Daily Staple",
                quantity=Decimal("100"),
                quantity_unit=QuantityUnit.g,
                source=MealItemSource.label,
            )
            db_session.add(item)

        db_session.flush()

        # Execute the range query
        result = get_range(
            db_session,
            from_date=start,
            to_date=end,
            granularity="day",
        )

        # Verify: 90 periods, each with 500 cal
        assert len(result.periods) == 90
        for period in result.periods:
            assert period.totals.calories == Decimal("500")
            assert period.totals.protein_g == Decimal("25")
            assert period.adherence is True  # 500 <= 2000

        # Also test weekly
        result_weekly = get_range(
            db_session,
            from_date=start,
            to_date=end,
            granularity="week",
        )

        # Sum should be 90 * 500 = 45000
        total_cal = sum(p.totals.calories for p in result_weekly.periods)
        assert total_cal == Decimal("45000")
