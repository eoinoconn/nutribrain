"""Tests for T-025: targets domain (set_target, get_effective_target).

Covers:
- no-target: get_effective_target returns None when no target row exists
- multiple-targets-same-day: latest created_at wins; set_target reports overlap
- missing cache row: falls back to base_calories alone (calories_out is None)
- cached-zero: a 0 calories_out is a genuine rest day, distinct from missing
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.db import IntervalsCaloriesOut, Target
from app.domain.targets import get_effective_target, set_target


class TestGetEffectiveTargetNoTarget:
    """When no target exists, get_effective_target returns None."""

    def test_no_target_returns_none(self, db_session: Session) -> None:
        result = get_effective_target(db_session, day=date(2026, 7, 26))
        assert result is None

    def test_target_in_future_returns_none(self, db_session: Session, make_target) -> None:
        """A target with effective_from after the query day is not visible."""
        make_target(effective_from=date(2026, 8, 1))
        result = get_effective_target(db_session, day=date(2026, 7, 26))
        assert result is None


class TestGetEffectiveTargetMissingCacheRow:
    """When a target exists but no intervals cache row, falls back to base alone."""

    def test_missing_cache_returns_base_only(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)
        result = get_effective_target(db_session, day=date(2026, 7, 26))

        assert result is not None
        assert result.base_calories == 2000
        assert result.calories_out is None
        assert result.effective_calories == 2000

    def test_effective_from_propagated(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2026, 3, 15), protein_g=160, carbs_g=250, fat_g=80)
        result = get_effective_target(db_session, day=date(2026, 7, 26))

        assert result is not None
        assert result.effective_from == date(2026, 3, 15)
        assert result.protein_g == 160
        assert result.carbs_g == 250
        assert result.fat_g == 80


class TestGetEffectiveTargetCachedZero:
    """A cached 0 is a genuine rest day — distinct from a missing cache row."""

    def test_cached_zero_calories_out(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)

        # Insert a zero-calorie rest day
        cache_row = IntervalsCaloriesOut(
            date=date(2026, 7, 26),
            calories_out=0,
            fetched_at=datetime(2026, 7, 26, 3, 0, tzinfo=UTC),
        )
        db_session.add(cache_row)
        db_session.flush()

        result = get_effective_target(db_session, day=date(2026, 7, 26))

        assert result is not None
        assert result.calories_out == 0
        assert result.effective_calories == 2000  # base + 0


class TestGetEffectiveTargetWithActivity:
    """When a cache row exists, effective_calories = base + calories_out."""

    def test_activity_added_to_base(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2026, 1, 1), base_calories=2000)

        cache_row = IntervalsCaloriesOut(
            date=date(2026, 7, 26),
            calories_out=500,
            fetched_at=datetime(2026, 7, 26, 3, 0, tzinfo=UTC),
        )
        db_session.add(cache_row)
        db_session.flush()

        result = get_effective_target(db_session, day=date(2026, 7, 26))

        assert result is not None
        assert result.base_calories == 2000
        assert result.calories_out == 500
        assert result.effective_calories == 2500


class TestGetEffectiveTargetMultipleTargets:
    """Multiple targets: the latest effective_from <= day wins."""

    def test_picks_most_recent_effective_from(self, db_session: Session, make_target) -> None:
        make_target(effective_from=date(2026, 1, 1), base_calories=1800)
        make_target(effective_from=date(2026, 6, 1), base_calories=2200)

        result = get_effective_target(db_session, day=date(2026, 7, 26))
        assert result is not None
        assert result.base_calories == 2200
        assert result.effective_from == date(2026, 6, 1)

    def test_multiple_same_day_latest_created_wins(self, db_session: Session) -> None:
        """When two targets share effective_from, the most recently created wins."""
        # Insert first target
        t1 = Target(
            effective_from=date(2026, 7, 1),
            base_calories=2000,
            protein_g=150,
            carbs_g=220,
            fat_g=70,
        )
        db_session.add(t1)
        db_session.flush()

        # Insert second target with same effective_from (later created_at)
        t2 = Target(
            effective_from=date(2026, 7, 1),
            base_calories=2500,
            protein_g=180,
            carbs_g=260,
            fat_g=85,
        )
        db_session.add(t2)
        db_session.flush()

        result = get_effective_target(db_session, day=date(2026, 7, 26))
        assert result is not None
        # The second target (2500) should win because it was created later
        assert result.base_calories == 2500


class TestSetTarget:
    """set_target always inserts a new row, never mutates."""

    def test_creates_new_target(self, db_session: Session) -> None:
        result = set_target(
            db_session,
            base_calories=2200,
            protein_g=150,
            carbs_g=220,
            fat_g=70,
            effective_from=date(2026, 7, 1),
        )

        assert result.id is not None
        assert result.base_calories == 2200
        assert result.protein_g == 150
        assert result.carbs_g == 220
        assert result.fat_g == 70
        assert result.effective_from == date(2026, 7, 1)
        assert result.same_day_overlap is False

    def test_same_day_overlap_reported(self, db_session: Session, make_target) -> None:
        """set_target reports when a target already exists for the same day."""
        make_target(effective_from=date(2026, 7, 1), base_calories=2000)

        result = set_target(
            db_session,
            base_calories=2500,
            protein_g=180,
            carbs_g=260,
            fat_g=85,
            effective_from=date(2026, 7, 1),
        )

        assert result.same_day_overlap is True
        assert result.base_calories == 2500

    def test_never_mutates_existing(self, db_session: Session, make_target) -> None:
        """Inserting a new target with the same date does not modify the old one."""
        original = make_target(effective_from=date(2026, 7, 1), base_calories=2000)
        original_id = original.id

        set_target(
            db_session,
            base_calories=2500,
            protein_g=180,
            carbs_g=260,
            fat_g=85,
            effective_from=date(2026, 7, 1),
        )

        # Original is unchanged
        db_session.expire(original)
        reloaded = db_session.get(Target, original_id)
        assert reloaded is not None
        assert reloaded.base_calories == 2000
