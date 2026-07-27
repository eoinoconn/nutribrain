"""add intervals_sync_status table

Singleton (id=1) row tracking the outcome of the last sync_intervals call
(§8, T-045). The cron trigger runs as a separate Render process from the web
dyno, so this state must live in Postgres for GET /api/sync/status to see it.

Revision ID: 898a49964f47
Revises: 0001_initial
Create Date: 2026-07-27 20:35:35.309375

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "898a49964f47"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intervals_sync_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intervals_sync_status")),
    )


def downgrade() -> None:
    op.drop_table("intervals_sync_status")
