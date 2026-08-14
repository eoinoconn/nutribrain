"""add app_settings table

Singleton (id=1) row of account-level app settings (§6a, EC-06). Single-user
app, no user_id, so one row covers every account-level setting; the energy
chart's compute_energy_timeline (EC-05, not built yet) will read
local_timezone here for local-midnight bounds on any day with no logged meal
to infer a timezone from. Mirrors intervals_sync_status's id=1 convention
rather than adding a CHECK(id = 1) constraint, since that table enforces
single-row-ness purely by domain-layer convention, not a DB constraint.

Revision ID: 3fabda81e50d
Revises: a9076a0773b9
Create Date: 2026-08-02 18:47:20.505306

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3fabda81e50d"
down_revision: str | None = "a9076a0773b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("local_timezone", sa.Text(), server_default="UTC", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_settings")),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
