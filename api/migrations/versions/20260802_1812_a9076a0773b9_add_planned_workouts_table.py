"""add planned_workouts table

Adds the planned_workouts table (§3 energy_balance_chart.md, EC-01): planned
and completed intervals.icu workouts plus manual entries, upserted on
``(source, external_id)`` so re-syncing doesn't duplicate rows. Purely
additive — does not touch intervals_calories_out or any merged migration.

Revision ID: a9076a0773b9
Revises: 007e2143f4d0
Create Date: 2026-08-02 18:12:17.829130

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a9076a0773b9"
down_revision: str | None = "007e2143f4d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: created/dropped explicitly below so upgrade and downgrade
# both own the type lifecycle (see 0001_initial for the same pattern).
planned_workout_source = postgresql.ENUM(
    "intervals_planned",
    "intervals_completed",
    "manual",
    name="planned_workout_source",
    create_type=False,
)
planned_workout_status = postgresql.ENUM(
    "planned", "completed", name="planned_workout_status", create_type=False
)

_ENUMS = (planned_workout_source, planned_workout_status)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in _ENUMS:
        enum.create(bind, checkfirst=False)

    op.create_table(
        "planned_workouts",
        sa.Column("id", sa.Integer(), nullable=False),
        # intervals.icu event/activity id; unique per source, absent for manual rows.
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("source", planned_workout_source, nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("sport_type", sa.Text(), nullable=True),
        sa.Column("icu_joules", sa.Integer(), nullable=True),
        sa.Column("estimated_calories", sa.Integer(), nullable=True),
        sa.Column("actual_calories", sa.Integer(), nullable=True),
        sa.Column("status", planned_workout_status, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_planned_workouts"),
        sa.UniqueConstraint("source", "external_id", name="uq_planned_workouts_source_external_id"),
    )
    op.create_index(
        "ix_planned_workouts_local_date", "planned_workouts", ["local_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_planned_workouts_local_date", table_name="planned_workouts")
    op.drop_table("planned_workouts")

    bind = op.get_bind()
    for enum in reversed(_ENUMS):
        enum.drop(bind, checkfirst=False)
