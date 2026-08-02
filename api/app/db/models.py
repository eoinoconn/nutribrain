"""SQLAlchemy models and native Postgres enums for the nutrition schema.

The database is the source of truth. Nullability, enum domains, and the
ad-hoc-macro invariant (see sections 3 and 6 and G1-G5) are all encoded here so
the schema, not just the domain layer, enforces the product rules.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# --- Numeric precision -----------------------------------------------------
# Every macro/quantity column is Numeric mapped to Decimal; domain math never
# uses float (style §4). Precision/scale are explicit so migrations are stable.
_CALORIES = Numeric(10, 2)
_MACRO = Numeric(10, 3)
_SODIUM = Numeric(10, 2)
_SERVING_SIZE = Numeric(10, 3)
_QUANTITY = Numeric(12, 4)
_DENSITY = Numeric(6, 4)


# --- Enums -----------------------------------------------------------------
class ServingUnit(enum.StrEnum):
    """Immutable reference unit for a food (Appendix B, G4)."""

    g = "g"
    ml = "ml"
    piece = "piece"


class MealType(enum.StrEnum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"


class QuantityUnit(enum.StrEnum):
    """Full logging unit set (G4). Deliberately complete from the outset."""

    g = "g"
    kg = "kg"
    oz = "oz"
    lb = "lb"
    ml = "ml"
    liter = "l"
    fl_oz = "fl_oz"
    tsp = "tsp"
    tbsp = "tbsp"
    cup = "cup"
    piece = "piece"
    serving = "serving"


class MealItemSource(enum.StrEnum):
    label = "label"
    template = "template"
    estimate = "estimate"
    manual = "manual"


class IntervalsSource(enum.StrEnum):
    sync = "sync"
    manual = "manual"


class PlannedWorkoutSource(enum.StrEnum):
    intervals_planned = "intervals_planned"
    intervals_completed = "intervals_completed"
    manual = "manual"


class PlannedWorkoutStatus(enum.StrEnum):
    planned = "planned"
    completed = "completed"


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Native Postgres enum that stores the member *value*, not its name."""

    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda members: [m.value for m in members],
    )


# --- Models ----------------------------------------------------------------
class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (
        # Fuzzy resolution reads through lower(name) (§3 indices, T-021).
        Index("ix_foods_lower_name", text("lower(name)")),
        # Cheap favorite lookup: partial index over the favorites only (§3).
        Index("ix_foods_is_favorite", "is_favorite", postgresql_where=text("is_favorite")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    serving_size: Mapped[Decimal] = mapped_column(_SERVING_SIZE)
    serving_unit: Mapped[ServingUnit] = mapped_column(_pg_enum(ServingUnit, "serving_unit"))
    calories: Mapped[Decimal] = mapped_column(_CALORIES)
    protein_g: Mapped[Decimal] = mapped_column(_MACRO)
    carbs_g: Mapped[Decimal] = mapped_column(_MACRO)
    fat_g: Mapped[Decimal] = mapped_column(_MACRO)
    fiber_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    sat_fat_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    sodium_mg: Mapped[Decimal | None] = mapped_column(_SODIUM, nullable=True)
    # Null density is treated as 1.0 by the domain layer (G4).
    density_g_per_ml: Mapped[Decimal | None] = mapped_column(_DENSITY, nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Soft delete (G1): reads filter deleted_at IS NULL; history still resolves.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    local_tz: Mapped[str] = mapped_column(Text)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[MealType] = mapped_column(_pg_enum(MealType, "meal_type"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Meals hard-delete their items; passive_deletes lets Postgres ON DELETE
    # CASCADE do the work instead of the ORM loading rows first.
    items: Mapped[list[MealItem]] = relationship(
        back_populates="meal",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MealItem(Base):
    __tablename__ = "meal_items"
    __table_args__ = (
        # Ad-hoc invariant (§6): macros populated iff food_id IS NULL.
        CheckConstraint(
            "(food_id IS NULL "
            "AND calories IS NOT NULL AND protein_g IS NOT NULL "
            "AND carbs_g IS NOT NULL AND fat_g IS NOT NULL) "
            "OR (food_id IS NOT NULL "
            "AND calories IS NULL AND protein_g IS NULL AND carbs_g IS NULL "
            "AND fat_g IS NULL AND fiber_g IS NULL AND sat_fat_g IS NULL "
            "AND sodium_mg IS NULL)",
            name="adhoc_macros",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"), index=True)
    # Null food_id = ad-hoc estimate; macros below are then required.
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(_QUANTITY)
    quantity_unit: Mapped[QuantityUnit] = mapped_column(_pg_enum(QuantityUnit, "quantity_unit"))
    calories: Mapped[Decimal | None] = mapped_column(_CALORIES, nullable=True)
    protein_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    carbs_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    fat_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    fiber_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    sat_fat_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    sodium_mg: Mapped[Decimal | None] = mapped_column(_SODIUM, nullable=True)
    source: Mapped[MealItemSource] = mapped_column(_pg_enum(MealItemSource, "meal_item_source"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meal: Mapped[Meal] = relationship(back_populates="items")
    food: Mapped[Food | None] = relationship()


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Soft delete (G1): past applications are already materialized as meal_items.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[TemplateItem]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TemplateItem(Base):
    __tablename__ = "template_items"
    __table_args__ = (
        # Same ad-hoc invariant as meal_items (§6).
        CheckConstraint(
            "(food_id IS NULL "
            "AND calories IS NOT NULL AND protein_g IS NOT NULL "
            "AND carbs_g IS NOT NULL AND fat_g IS NOT NULL) "
            "OR (food_id IS NOT NULL "
            "AND calories IS NULL AND protein_g IS NULL AND carbs_g IS NULL "
            "AND fat_g IS NULL AND fiber_g IS NULL AND sat_fat_g IS NULL "
            "AND sodium_mg IS NULL)",
            name="adhoc_macros",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(_QUANTITY)
    quantity_unit: Mapped[QuantityUnit] = mapped_column(_pg_enum(QuantityUnit, "quantity_unit"))
    calories: Mapped[Decimal | None] = mapped_column(_CALORIES, nullable=True)
    protein_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    carbs_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    fat_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    fiber_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    sat_fat_g: Mapped[Decimal | None] = mapped_column(_MACRO, nullable=True)
    sodium_mg: Mapped[Decimal | None] = mapped_column(_SODIUM, nullable=True)

    template: Mapped[Template] = relationship(back_populates="items")
    food: Mapped[Food | None] = relationship()


class Target(Base):
    __tablename__ = "targets"
    # get_effective_target scans for the latest effective_from <= day (§3, T-025),
    # so the index is DESC. Alembic compares index ordering, so the model must
    # declare DESC to match the migration and keep autogenerate empty.
    __table_args__ = (Index("ix_targets_effective_from", text("effective_from DESC")),)

    id: Mapped[int] = mapped_column(primary_key=True)
    effective_from: Mapped[date] = mapped_column(Date)
    base_calories: Mapped[int] = mapped_column(Integer)
    protein_g: Mapped[int] = mapped_column(Integer)
    carbs_g: Mapped[int] = mapped_column(Integer)
    fat_g: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntervalsCaloriesOut(Base):
    __tablename__ = "intervals_calories_out"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    calories_out: Mapped[int] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # sync = worker-written truth, manual = dashboard override (G5).
    source: Mapped[IntervalsSource] = mapped_column(
        _pg_enum(IntervalsSource, "intervals_source"),
        default=IntervalsSource.sync,
        server_default=IntervalsSource.sync.value,
    )


class PlannedWorkout(Base):
    """A planned or completed workout, sourced from intervals.icu or manual entry.

    (§3 energy_balance_chart.md). Re-syncing intervals.icu upserts on
    ``(source, external_id)`` rather than duplicating rows.
    """

    __tablename__ = "planned_workouts"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_planned_workouts_source_external_id",
        ),
        Index("ix_planned_workouts_local_date", "local_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # intervals.icu event/activity id; unique per source, absent for manual rows.
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[PlannedWorkoutSource] = mapped_column(
        _pg_enum(PlannedWorkoutSource, "planned_workout_source")
    )
    local_date: Mapped[date] = mapped_column(Date)
    # Null start times are not usable for this feature; reject/skip at sync time.
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    # intervals.icu `type` (Ride/Run/Swim/...); nullable for manual rows.
    sport_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # intervals.icu's own computed work estimate; requires structured targets
    # plus configured zones, so it's often absent on unstructured placeholders.
    icu_joules: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Completed rows: the same device-reported calories field, kept
    # per-activity instead of summed. Not a new sourcing mechanism.
    actual_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[PlannedWorkoutStatus] = mapped_column(
        _pg_enum(PlannedWorkoutStatus, "planned_workout_status")
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntervalsSyncStatus(Base):
    """Singleton row (id=1) tracking the last sync_intervals outcome (§8, T-045).

    The cron trigger runs as a separate Render process from the web dyno, so
    this must be persisted rather than held in memory for
    ``GET /api/sync/status`` to see cron-driven syncs.
    """

    __tablename__ = "intervals_sync_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppSettings(Base):
    """Singleton row (id=1) of account-level app settings (§6a, EC-06).

    Single-user app, no ``user_id`` — one row holds every account-level
    setting. Mirrors the ``id=1`` convention used by ``IntervalsSyncStatus``
    rather than adding a ``CHECK (id = 1)`` constraint, since that existing
    singleton table enforces single-row-ness purely by domain-layer
    convention (always ``session.get(Model, 1)``), not a DB constraint.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_timezone: Mapped[str] = mapped_column(Text, default="UTC", server_default="UTC")


class McpOAuthKV(Base):
    """Backing store for FastMCP's ``GoogleProvider`` ``client_storage`` (F-101).

    ``OAuthProxy`` uses this as a generic ``AsyncKeyValue`` store for OAuth
    proxy state (registered DCR clients, encrypted upstream tokens,
    authorization codes, ...), partitioned by ``collection``. Postgres is used
    instead of the library's default encrypted-file store because Render's
    filesystem is ephemeral across deploys (see
    ``docs/features/mcp_oauth.md`` "Motivation").
    """

    __tablename__ = "mcp_oauth_kv"

    collection: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    # NULL means no expiry. TTL is enforced lazily on read (see
    # app/mcp_auth/storage.py) rather than by an active sweeper.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
