"""add mcp_oauth_kv table

Backing store for FastMCP's ``GoogleProvider`` ``client_storage`` (F-101,
``docs/features/mcp_oauth.md``). Replaces the library's default encrypted
file store, which doesn't survive Render's ephemeral filesystem across
deploys, with the one Postgres database that's otherwise this app's single
source of truth.

Revision ID: 007e2143f4d0
Revises: 898a49964f47
Create Date: 2026-07-29 21:44:31.182926

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007e2143f4d0"
down_revision: str | None = "898a49964f47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_kv",
        sa.Column("collection", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("collection", "key", name=op.f("pk_mcp_oauth_kv")),
    )


def downgrade() -> None:
    op.drop_table("mcp_oauth_kv")
