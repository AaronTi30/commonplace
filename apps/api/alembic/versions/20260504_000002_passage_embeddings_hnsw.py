"""partial HNSW index for MiniLM passage embeddings

Revision ID: 20260504_000002
Revises: 20260430_000001
Create Date: 2026-05-04

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260504_000002"
down_revision = "20260430_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
CREATE INDEX IF NOT EXISTS ix_passage_embeddings_hnsw_miniilm_cosine
ON passage_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE embedding_model = 'sentence-transformers/all-MiniLM-L6-v2';
"""
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_passage_embeddings_hnsw_miniilm_cosine"))
