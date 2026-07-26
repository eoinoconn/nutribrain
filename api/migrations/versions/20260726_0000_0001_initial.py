"""initial schema

Creates all seven tables from spec §3, the five native Postgres enums
(Appendix B, with G4/G5 widenings), the ad-hoc-macro CHECK constraints, and
every index listed in §3 "Indices". The downgrade is a full teardown, not a
stub, so ``alembic downgrade base`` returns an empty database.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-26 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- Enums -----------------------------------------------------------------
# create_type=False: we create/drop the types explicitly below so both the
# upgrade and downgrade own the type lifecycle (create_table would otherwise
# create them implicitly but never drop them).
serving_unit = postgresql.ENUM("g", "ml", "piece", name="serving_unit", create_type=False)
meal_type = postgresql.ENUM(
    "breakfast", "lunch", "dinner", "snack", name="meal_type", create_type=False
)
quantity_unit = postgresql.ENUM(
    "g",
    "kg",
    "oz",
    "lb",
    "ml",
    "l",
    "fl_oz",
    "tsp",
    "tbsp",
    "cup",
    "piece",
    "serving",
    name="quantity_unit",
    create_type=False,
)
meal_item_source = postgresql.ENUM(
    "label", "template", "estimate", "manual", name="meal_item_source", create_type=False
)
intervals_source = postgresql.ENUM("sync", "manual", name="intervals_source", create_type=False)

_ENUMS = (serving_unit, meal_type, quantity_unit, meal_item_source, intervals_source)

# Precision/scale mirror app.db.models exactly so autogenerate stays quiet.
_CALORIES = sa.Numeric(10, 2)
_MACRO = sa.Numeric(10, 3)
_SODIUM = sa.Numeric(10, 2)
_SERVING_SIZE = sa.Numeric(10, 3)
_QUANTITY = sa.Numeric(12, 4)
_DENSITY = sa.Numeric(6, 4)

# The ad-hoc invariant (§6): macros are populated iff food_id IS NULL. Shared
# verbatim by meal_items and template_items.
_ADHOC_MACROS = (
    "(food_id IS NULL "
    "AND calories IS NOT NULL AND protein_g IS NOT NULL "
    "AND carbs_g IS NOT NULL AND fat_g IS NOT NULL) "
    "OR (food_id IS NOT NULL "
    "AND calories IS NULL AND protein_g IS NULL AND carbs_g IS NULL "
    "AND fat_g IS NULL AND fiber_g IS NULL AND sat_fat_g IS NULL "
    "AND sodium_mg IS NULL)"
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in _ENUMS:
        enum.create(bind, checkfirst=False)

    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("serving_size", _SERVING_SIZE, nullable=False),
        sa.Column("serving_unit", serving_unit, nullable=False),
        sa.Column("calories", _CALORIES, nullable=False),
        sa.Column("protein_g", _MACRO, nullable=False),
        sa.Column("carbs_g", _MACRO, nullable=False),
        sa.Column("fat_g", _MACRO, nullable=False),
        sa.Column("fiber_g", _MACRO, nullable=True),
        sa.Column("sat_fat_g", _MACRO, nullable=True),
        sa.Column("sodium_mg", _SODIUM, nullable=True),
        sa.Column("density_g_per_ml", _DENSITY, nullable=True),
        sa.Column(
            "is_favorite",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_foods"),
    )
    op.create_index("ix_foods_lower_name", "foods", [sa.text("lower(name)")], unique=False)
    op.create_index(
        "ix_foods_is_favorite",
        "foods",
        ["is_favorite"],
        unique=False,
        postgresql_where=sa.text("is_favorite"),
    )

    op.create_table(
        "meals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_tz", sa.Text(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("meal_type", meal_type, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_meals"),
    )
    op.create_index("ix_meals_local_date", "meals", ["local_date"], unique=False)

    op.create_table(
        "meal_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meal_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("quantity", _QUANTITY, nullable=False),
        sa.Column("quantity_unit", quantity_unit, nullable=False),
        sa.Column("calories", _CALORIES, nullable=True),
        sa.Column("protein_g", _MACRO, nullable=True),
        sa.Column("carbs_g", _MACRO, nullable=True),
        sa.Column("fat_g", _MACRO, nullable=True),
        sa.Column("fiber_g", _MACRO, nullable=True),
        sa.Column("sat_fat_g", _MACRO, nullable=True),
        sa.Column("sodium_mg", _SODIUM, nullable=True),
        sa.Column("source", meal_item_source, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(_ADHOC_MACROS, name="adhoc_macros"),
        sa.ForeignKeyConstraint(
            ["meal_id"],
            ["meals.id"],
            name="fk_meal_items_meal_id_meals",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"], name="fk_meal_items_food_id_foods"),
        sa.PrimaryKeyConstraint("id", name="pk_meal_items"),
    )
    op.create_index("ix_meal_items_meal_id", "meal_items", ["meal_id"], unique=False)

    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_templates"),
    )

    op.create_table(
        "template_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("quantity", _QUANTITY, nullable=False),
        sa.Column("quantity_unit", quantity_unit, nullable=False),
        sa.Column("calories", _CALORIES, nullable=True),
        sa.Column("protein_g", _MACRO, nullable=True),
        sa.Column("carbs_g", _MACRO, nullable=True),
        sa.Column("fat_g", _MACRO, nullable=True),
        sa.Column("fiber_g", _MACRO, nullable=True),
        sa.Column("sat_fat_g", _MACRO, nullable=True),
        sa.Column("sodium_mg", _SODIUM, nullable=True),
        sa.CheckConstraint(_ADHOC_MACROS, name="adhoc_macros"),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
            name="fk_template_items_template_id_templates",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"], name="fk_template_items_food_id_foods"),
        sa.PrimaryKeyConstraint("id", name="pk_template_items"),
    )
    op.create_index(
        "ix_template_items_template_id", "template_items", ["template_id"], unique=False
    )

    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("base_calories", sa.Integer(), nullable=False),
        sa.Column("protein_g", sa.Integer(), nullable=False),
        sa.Column("carbs_g", sa.Integer(), nullable=False),
        sa.Column("fat_g", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_targets"),
    )
    # DESC to match the "most recent effective_from <= day" scan (§3, T-025).
    op.create_index(
        "ix_targets_effective_from",
        "targets",
        [sa.text("effective_from DESC")],
        unique=False,
    )

    op.create_table(
        "intervals_calories_out",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("calories_out", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            intervals_source,
            server_default=sa.text("'sync'"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("date", name="pk_intervals_calories_out"),
    )


def downgrade() -> None:
    op.drop_table("intervals_calories_out")
    op.drop_index("ix_targets_effective_from", table_name="targets")
    op.drop_table("targets")
    op.drop_index("ix_template_items_template_id", table_name="template_items")
    op.drop_table("template_items")
    op.drop_table("templates")
    op.drop_index("ix_meal_items_meal_id", table_name="meal_items")
    op.drop_table("meal_items")
    op.drop_index("ix_meals_local_date", table_name="meals")
    op.drop_table("meals")
    op.drop_index("ix_foods_is_favorite", table_name="foods")
    op.drop_index("ix_foods_lower_name", table_name="foods")
    op.drop_table("foods")

    bind = op.get_bind()
    for enum in reversed(_ENUMS):
        enum.drop(bind, checkfirst=False)
