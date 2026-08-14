"""Tests for MCP-03: find_meal.

Covers matching against meal_items.name (populated for both food-linked and
ad-hoc items), most-recent-first ordering, since/limit bounding, no-match
returning an empty list, and fuzzy/typo tolerance consistent with
search_foods' threshold.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.meal_search import find_meal


class TestFindMealMatching:
    def test_matches_ad_hoc_item_by_stored_name(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        meal = make_meal(logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC))
        item = make_meal_item(meal=meal, name="Protein Shake", food_id=None)

        results = find_meal(db_session, query="protein shake")

        assert len(results) == 1
        assert results[0].item_id == item.id
        assert results[0].meal_id == meal.id
        assert results[0].food_id is None
        assert results[0].name == "Protein Shake"

    def test_matches_food_linked_item_by_snapshotted_name(
        self, db_session: Session, make_food, make_meal, make_meal_item
    ) -> None:
        # log_meal snapshots the resolved food's name onto meal_items.name at
        # write time, so matching meal_items.name alone (no join to foods) is
        # sufficient for food-linked items too.
        food = make_food(name="Chicken Breast")
        meal = make_meal(logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC))
        item = make_meal_item(meal=meal, food=food, name=food.name, quantity=Decimal("150"))

        results = find_meal(db_session, query="chicken")

        assert len(results) == 1
        assert results[0].item_id == item.id
        assert results[0].food_id == food.id
        assert results[0].macros.calories is not None

    def test_no_match_returns_empty_list(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        meal = make_meal()
        make_meal_item(meal=meal, name="Protein Shake", food_id=None)

        results = find_meal(db_session, query="nonexistent zzz food")

        assert results == []

    def test_fuzzy_typo_tolerance_matches_like_search_foods(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        meal = make_meal()
        item = make_meal_item(meal=meal, name="Brennans Bagel", food_id=None)

        results = find_meal(db_session, query="bagel")

        assert len(results) == 1
        assert results[0].item_id == item.id


class TestFindMealOrderingAndBounding:
    def test_most_recent_first_ordering(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        older_meal = make_meal(logged_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC))
        newer_meal = make_meal(logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC))
        older_item = make_meal_item(meal=older_meal, name="Protein Shake", food_id=None)
        newer_item = make_meal_item(meal=newer_meal, name="Protein Shake", food_id=None)

        results = find_meal(db_session, query="protein shake")

        assert [r.item_id for r in results] == [newer_item.id, older_item.id]

    def test_since_bounds_results_to_local_date(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        old_meal = make_meal(logged_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC))
        recent_meal = make_meal(logged_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC))
        make_meal_item(meal=old_meal, name="Protein Shake", food_id=None)
        recent_item = make_meal_item(meal=recent_meal, name="Protein Shake", food_id=None)

        results = find_meal(db_session, query="protein shake", since=date(2026, 7, 1))

        assert len(results) == 1
        assert results[0].item_id == recent_item.id

    def test_limit_bounds_result_count(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        for day in range(1, 6):
            meal = make_meal(logged_at=datetime(2026, 7, day, 12, 0, tzinfo=UTC))
            make_meal_item(meal=meal, name="Protein Shake", food_id=None)

        results = find_meal(db_session, query="protein shake", limit=2)

        assert len(results) == 2

    def test_empty_query_returns_most_recent_items_up_to_limit(
        self, db_session: Session, make_meal, make_meal_item
    ) -> None:
        meal = make_meal()
        item = make_meal_item(meal=meal, name="Protein Shake", food_id=None)

        results = find_meal(db_session, query="")

        assert len(results) == 1
        assert results[0].item_id == item.id
