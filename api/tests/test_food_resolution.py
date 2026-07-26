from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain import FoodAmbiguousError, FoodNotFoundError, resolve_food

_NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def test_resolve_food_explicit_food_id_wins(
    db_session: Session,
    make_food,
) -> None:
    winner = make_food(name="Rice Cake")
    make_food(name="Rice")

    resolved = resolve_food(
        db_session,
        food_id=winner.id,
        name="Rice",
        has_supplied_macros=False,
        now=_NOW,
    )

    assert resolved is not None
    assert resolved.id == winner.id


def test_resolve_food_single_fuzzy_match_wins(
    db_session: Session,
    make_food,
) -> None:
    winner = make_food(name="Brennans Bagel")
    make_food(name="Chicken Breast")

    resolved = resolve_food(
        db_session,
        food_id=None,
        name="bagel",
        has_supplied_macros=False,
        now=_NOW,
    )

    assert resolved is not None
    assert resolved.id == winner.id


def test_resolve_food_multiple_matches_with_one_favorite_wins(
    db_session: Session,
    make_food,
) -> None:
    favorite = make_food(name="Brennans Bagel", is_favorite=True)
    make_food(name="M&S Sourdough Bagel", is_favorite=False)

    resolved = resolve_food(
        db_session,
        food_id=None,
        name="bagel",
        has_supplied_macros=False,
        now=_NOW,
    )

    assert resolved is not None
    assert resolved.id == favorite.id


def test_resolve_food_multiple_matches_one_recently_logged_wins(
    db_session: Session,
    make_food,
    make_meal,
    make_meal_item,
) -> None:
    recent = make_food(name="Brennans Bagel")
    stale = make_food(name="M&S Sourdough Bagel")

    meal = make_meal(logged_at=_NOW - timedelta(days=7))
    make_meal_item(meal_id=meal.id, food_id=recent.id)

    old_meal = make_meal(logged_at=_NOW - timedelta(days=45))
    make_meal_item(meal_id=old_meal.id, food_id=stale.id)

    resolved = resolve_food(
        db_session,
        food_id=None,
        name="bagel",
        has_supplied_macros=False,
        now=_NOW,
    )

    assert resolved is not None
    assert resolved.id == recent.id


def test_resolve_food_ambiguous_when_multiple_matches_and_no_tiebreaker(
    db_session: Session,
    make_food,
) -> None:
    first = make_food(name="Brennans Bagel")
    second = make_food(name="M&S Sourdough Bagel")

    with pytest.raises(FoodAmbiguousError) as excinfo:
        resolve_food(
            db_session,
            food_id=None,
            name="bagel",
            has_supplied_macros=False,
            now=_NOW,
        )

    err = excinfo.value
    assert err.error == "food_ambiguous"
    assert err.candidates == [
        {"id": first.id, "name": first.name, "calories": first.calories},
        {"id": second.id, "name": second.name, "calories": second.calories},
    ]


def test_resolve_food_two_favorites_stays_ambiguous(
    db_session: Session,
    make_food,
) -> None:
    make_food(name="Brennans Bagel", is_favorite=True)
    make_food(name="M&S Sourdough Bagel", is_favorite=True)

    with pytest.raises(FoodAmbiguousError):
        resolve_food(
            db_session,
            food_id=None,
            name="bagel",
            has_supplied_macros=False,
            now=_NOW,
        )


def test_resolve_food_no_match_without_macros_raises_food_not_found(
    db_session: Session,
) -> None:
    with pytest.raises(FoodNotFoundError) as excinfo:
        resolve_food(
            db_session,
            food_id=None,
            name="impossible food name",
            has_supplied_macros=False,
            now=_NOW,
        )

    assert excinfo.value.error == "food_not_found"


def test_resolve_food_no_match_with_macros_returns_none(
    db_session: Session,
) -> None:
    resolved = resolve_food(
        db_session,
        food_id=None,
        name="impossible food name",
        has_supplied_macros=True,
        now=_NOW,
    )

    assert resolved is None


def test_resolve_food_soft_deleted_foods_are_not_candidates(
    db_session: Session,
    make_food,
) -> None:
    deleted = make_food(name="Brennans Bagel", deleted_at=_NOW)
    active = make_food(name="M&S Sourdough Bagel")

    resolved = resolve_food(
        db_session,
        food_id=None,
        name="bagel",
        has_supplied_macros=False,
        now=_NOW,
    )

    assert resolved is not None
    assert resolved.id == active.id
    assert resolved.id != deleted.id
