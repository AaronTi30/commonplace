"""init

Revision ID: 20260430_000001
Revises: 
Create Date: 2026-04-30

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision = "20260430_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute(sa.text("CREATE TYPE source_type AS ENUM ('gutenberg', 'wikisource')"))
    op.execute(sa.text("CREATE TYPE ingestion_state AS ENUM ('queued', 'running', 'complete', 'failed')"))
    op.execute(sa.text("CREATE TYPE job_type AS ENUM ('ingest_work')"))
    op.execute(sa.text("CREATE TYPE job_status AS ENUM ('queued', 'running', 'succeeded', 'failed')"))
    op.execute(
        sa.text("CREATE TYPE progress_stage AS ENUM ('fetch', 'normalize', 'chunk', 'embed', 'upsert')")
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.Enum(name="source_type"), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("license_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_type", "locator", name="uq_sources_type_locator"),
    )

    op.create_table(
        "source_artifacts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieval_url", sa.Text(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "((raw_text IS NULL) <> (raw_html IS NULL))",
            name="ck_source_artifacts_exactly_one_raw",
        ),
    )

    op.create_table(
        "works",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("ingestion_state", sa.Enum(name="ingestion_state"), server_default="queued", nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", name="uq_works_source_id"),
    )

    op.create_table(
        "passages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "work_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_label", sa.Text(), nullable=True),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("cleaned_text", sa.Text(), nullable=False),
        sa.Column("citation_string", sa.Text(), nullable=False),
        sa.Column("chunker_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "passage_embeddings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "passage_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("passages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("passage_id", "embedding_model", name="uq_passage_embeddings_passage_model"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.Enum(name="job_type"), nullable=False),
        sa.Column("status", sa.Enum(name="job_status"), server_default="queued", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "work_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("progress_stage", sa.Enum(name="progress_stage"), server_default="fetch", nullable=False),
        sa.Column("progress", sa.dialects.postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "ix_ingestion_jobs_status_created_at",
        "ingestion_jobs",
        ["status", "created_at"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
CREATE OR REPLACE FUNCTION set_passage_embeddings_work_id()
RETURNS trigger AS $$
DECLARE
    v_work_id uuid;
BEGIN
    SELECT work_id INTO v_work_id FROM passages WHERE id = NEW.passage_id;
    IF v_work_id IS NULL THEN
        RAISE EXCEPTION 'passage_embeddings.passage_id % does not exist', NEW.passage_id;
    END IF;
    NEW.work_id := v_work_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
        )
    )

    op.execute(
        sa.text(
            """
CREATE TRIGGER trg_set_passage_embeddings_work_id
BEFORE INSERT OR UPDATE OF passage_id ON passage_embeddings
FOR EACH ROW
EXECUTE FUNCTION set_passage_embeddings_work_id();
"""
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_set_passage_embeddings_work_id ON passage_embeddings"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS set_passage_embeddings_work_id"))

    op.drop_index("ix_ingestion_jobs_status_created_at", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_table("passage_embeddings")
    op.drop_table("passages")
    op.drop_table("works")
    op.drop_table("source_artifacts")
    op.drop_table("sources")

    op.execute(sa.text("DROP TYPE IF EXISTS progress_stage"))
    op.execute(sa.text("DROP TYPE IF EXISTS job_status"))
    op.execute(sa.text("DROP TYPE IF EXISTS job_type"))
    op.execute(sa.text("DROP TYPE IF EXISTS ingestion_state"))
    op.execute(sa.text("DROP TYPE IF EXISTS source_type"))

