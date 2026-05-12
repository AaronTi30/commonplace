"""GIN expression index for full-text search on passages.cleaned_text

Revision ID: 20260511_000003
Revises: 20260504_000002
Create Date: 2026-05-11

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260511_000003"
down_revision = "20260504_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
CREATE INDEX IF NOT EXISTS ix_passages_fts_english
ON passages
USING gin(to_tsvector('english', cleaned_text));
"""
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_passages_fts_english"))
