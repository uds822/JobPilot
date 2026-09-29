"""Add durable user job state and independent source polling times.

Revision ID: a1000cw00004
Revises: a1000cw00003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1000cw00004"
down_revision: Union[str, Sequence[str], None] = "a1000cw00003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    source_columns = {
        column["name"] for column in inspector.get_columns("company_sources")
    }
    if "last_ingested_at" not in source_columns:
        op.add_column("company_sources", sa.Column("last_ingested_at", sa.DateTime()))
    if "next_verify_at" not in source_columns:
        op.add_column(
            "company_sources",
            sa.Column("next_verify_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    source_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("company_sources")
    }
    if "ix_company_sources_verify_due" not in source_indexes:
        op.create_index(
            "ix_company_sources_verify_due",
            "company_sources",
            ["is_active", "next_verify_at", "claimed_until"],
        )

    if not sa.inspect(bind).has_table("ai_user_job_states"):
        op.create_table(
            "ai_user_job_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="viewed"),
        sa.Column("first_shown_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_shown_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("show_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("saved_at", sa.DateTime()),
        sa.Column("applied_at", sa.DateTime()),
        sa.Column("dismissed_at", sa.DateTime()),
        sa.Column("application_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('viewed', 'saved', 'dismissed', 'applied')",
            name="ck_ai_user_job_state_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["ai_canonical_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "job_id", name="uq_ai_user_job_state_user_job"),
        )
    state_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("ai_user_job_states")
    }
    if "ix_ai_user_job_states_user_status" not in state_indexes:
        op.create_index(
            "ix_ai_user_job_states_user_status",
            "ai_user_job_states",
            ["user_id", "status"],
        )
    if "ix_ai_user_job_states_application_id" not in state_indexes:
        op.create_index(
            "ix_ai_user_job_states_application_id",
            "ai_user_job_states",
            ["application_id"],
        )
    job_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("ai_canonical_jobs")
    }
    if "ix_ai_canonical_jobs_active_seen" not in job_indexes:
        op.create_index(
            "ix_ai_canonical_jobs_active_seen",
            "ai_canonical_jobs",
            ["is_active", "last_seen_at"],
            postgresql_where=sa.text("ingestion_source_id IS NOT NULL"),
        )

    # Preserve durable actions that were previously stored only on individual
    # search-run matches. Applied outranks dismissed, which outranks saved.
    op.execute(
        """
        INSERT INTO ai_user_job_states (
            user_id, job_id, status, first_shown_at, last_shown_at, show_count,
            saved_at, applied_at, dismissed_at, created_at, updated_at
        )
        SELECT
            user_id,
            job_id,
            CASE
                WHEN bool_or(status = 'applied') THEN 'applied'
                WHEN bool_or(status = 'dismissed') THEN 'dismissed'
                WHEN bool_or(status = 'saved') THEN 'saved'
                ELSE 'viewed'
            END,
            min(created_at),
            max(created_at),
            count(*)::integer,
            min(created_at) FILTER (WHERE status = 'saved'),
            min(created_at) FILTER (WHERE status = 'applied'),
            min(created_at) FILTER (WHERE status = 'dismissed'),
            min(created_at),
            max(created_at)
        FROM ai_job_matches
        GROUP BY user_id, job_id
        ON CONFLICT (user_id, job_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_ai_canonical_jobs_active_seen", table_name="ai_canonical_jobs")
    op.drop_index("ix_ai_user_job_states_application_id", table_name="ai_user_job_states")
    op.drop_index("ix_ai_user_job_states_user_status", table_name="ai_user_job_states")
    op.drop_table("ai_user_job_states")
    op.drop_index("ix_company_sources_verify_due", table_name="company_sources")
    op.drop_column("company_sources", "next_verify_at")
    op.drop_column("company_sources", "last_ingested_at")
