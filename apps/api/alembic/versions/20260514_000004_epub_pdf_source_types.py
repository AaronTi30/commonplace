"""epub/pdf source types and raw_file_path on source_artifacts

Revision ID: 20260514_000004
Revises: 20260511_000003
Create Date: 2026-05-14

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260514_000004"
down_revision = "20260511_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
DO $$ BEGIN
    ALTER TYPE source_type ADD VALUE 'epub';
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
"""
        )
    )
    op.execute(
        sa.text(
            """
DO $$ BEGIN
    ALTER TYPE source_type ADD VALUE 'pdf';
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
"""
        )
    )

    op.add_column("source_artifacts", sa.Column("raw_file_path", sa.Text(), nullable=True))

    op.drop_constraint("ck_source_artifacts_exactly_one_raw", "source_artifacts", type_="check")
    op.create_check_constraint(
        "ck_source_artifacts_exactly_one_raw",
        "source_artifacts",
        "((raw_text IS NOT NULL)::int + (raw_html IS NOT NULL)::int + (raw_file_path IS NOT NULL)::int) = 1",
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM source_artifacts WHERE raw_file_path IS NOT NULL"))

    op.drop_constraint("ck_source_artifacts_exactly_one_raw", "source_artifacts", type_="check")
    op.drop_column("source_artifacts", "raw_file_path")

    op.create_check_constraint(
        "ck_source_artifacts_exactly_one_raw",
        "source_artifacts",
        "((raw_text IS NULL) <> (raw_html IS NULL))",
    )
