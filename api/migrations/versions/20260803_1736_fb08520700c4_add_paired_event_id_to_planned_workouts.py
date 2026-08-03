"""add paired_event_id to planned_workouts

intervals.icu's own link from a completed activity back to the calendar
event it fulfilled (Activity.paired_event_id in the vendored OpenAPI spec,
an int matching the event's own id -- a different id space from the
activity's own id/external_id). Lets sync_planned_workouts correctly flip a
planned row to completed and recognize an already-completed event on a
later /events sync, instead of the incorrect same-external_id guess EC-03
originally shipped with.

Revision ID: fb08520700c4
Revises: 3fabda81e50d
Create Date: 2026-08-03 17:36:15.369495

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fb08520700c4"
down_revision: str | None = "3fabda81e50d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("planned_workouts", sa.Column("paired_event_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("planned_workouts", "paired_event_id")
