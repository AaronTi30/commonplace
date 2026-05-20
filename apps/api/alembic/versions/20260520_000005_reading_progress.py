"""reading_progress table

Revision ID: 20260520_000005
Revises: 20260514_000004
Create Date: 2026-05-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260520_000005"
down_revision = "20260514_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reading_progress",
        sa.Column("work_id", UUID(as_uuid=True), sa.ForeignKey("works.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("position", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reading_progress")
