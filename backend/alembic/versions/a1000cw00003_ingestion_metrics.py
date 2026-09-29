"""Add Company Watch ingestion metrics.

Revision ID: a1000cw00003
Revises: a1000cw00002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1000cw00003"
down_revision: Union[str, Sequence[str], None] = "a1000cw00002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("company_watch_runs")}
    for name in ("jobs_inserted", "jobs_updated", "persistence_failures"):
        if name not in existing:
            op.add_column(
                "company_watch_runs",
                sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
            )

    job_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("ai_canonical_jobs")
    }
    if "first_seen_at" not in job_columns:
        op.add_column(
            "ai_canonical_jobs",
            sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "last_seen_at" not in job_columns:
        op.add_column(
            "ai_canonical_jobs",
            sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "missing_poll_count" not in job_columns:
        op.add_column(
            "ai_canonical_jobs",
            sa.Column("missing_poll_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "ingestion_source_id" not in job_columns:
        op.add_column("ai_canonical_jobs", sa.Column("ingestion_source_id", sa.Integer()))
        op.create_foreign_key(
            "fk_ai_canonical_jobs_ingestion_source",
            "ai_canonical_jobs",
            "company_sources",
            ["ingestion_source_id"],
            ["id"],
            ondelete="SET NULL",
        )

    existing_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("ai_canonical_jobs")
    }
    if "ix_ai_canonical_jobs_last_seen_at" not in existing_indexes:
        op.create_index("ix_ai_canonical_jobs_last_seen_at", "ai_canonical_jobs", ["last_seen_at"])
    if "ix_ai_canonical_jobs_ingestion_source_id" not in existing_indexes:
        op.create_index(
            "ix_ai_canonical_jobs_ingestion_source_id",
            "ai_canonical_jobs",
            ["ingestion_source_id"],
        )


def downgrade() -> None:
    # Freshness columns belong to a1000cw00002. This revision only owns the
    # run metrics below, even when its defensive upgrade found an older schema.
    op.drop_column("company_watch_runs", "persistence_failures")
    op.drop_column("company_watch_runs", "jobs_updated")
    op.drop_column("company_watch_runs", "jobs_inserted")
