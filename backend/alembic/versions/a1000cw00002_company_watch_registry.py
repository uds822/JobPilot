"""Add company intelligence registry and source verification state.

Revision ID: a1000cw00002
Revises: a1000ai00001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1000cw00002"
down_revision: Union[str, Sequence[str], None] = "a1000ai00001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_intelligence",
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("company_type", sa.String(40)),
        sa.Column("sub_industry", sa.String(100)),
        sa.Column("size_bucket", sa.String(30)),
        sa.Column("priority_tier", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("india_hiring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remote_india", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("engineering_relevance", sa.Float(), nullable=False, server_default="1"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("priority_tier BETWEEN 1 AND 3", name="ck_company_intelligence_priority"),
        sa.CheckConstraint(
            "engineering_relevance BETWEEN 0 AND 1",
            name="ck_company_intelligence_relevance",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("company_id"),
    )
    op.create_table(
        "company_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(200), nullable=False),
        sa.Column("normalized_alias", sa.String(200), nullable=False),
        sa.Column("source", sa.String(50)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("normalized_alias", name="uq_company_alias_normalized"),
    )
    op.create_index("ix_company_aliases_company_id", "company_aliases", ["company_id"])
    op.create_table(
        "company_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(80), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.Column("city", sa.String(100)),
        sa.Column("location_type", sa.String(30), nullable=False, server_default="office"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "company_id", "country", "region", "city", "location_type",
            name="uq_company_locations_identity",
        ),
    )
    op.create_index("ix_company_locations_company_id", "company_locations", ["company_id"])
    op.create_table(
        "company_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("identifier", sa.String(200), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="unverified"),
        sa.Column("managed_by_existing_provider", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_verified_at", sa.DateTime()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("last_failure_at", sa.DateTime()),
        sa.Column("last_job_seen_at", sa.DateTime()),
        sa.Column("next_check_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default="360"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_http_status", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("claimed_until", sa.DateTime()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("poll_interval_minutes > 0", name="ck_company_sources_poll_interval"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider", "identifier", name="uq_company_sources_provider_identifier"
        ),
    )
    op.create_index("ix_company_sources_company_id", "company_sources", ["company_id"])
    op.create_index(
        "ix_company_sources_due",
        "company_sources",
        ["is_active", "next_check_at", "claimed_until"],
    )
    op.create_table(
        "company_watch_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("sources_claimed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sources_successful", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sources_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("india_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
    )
    op.create_table(
        "company_source_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_source_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer()),
        sa.Column("checked_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("jobs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("india_jobs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(
            ["company_source_id"], ["company_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["company_watch_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_company_source_checks_company_source_id",
        "company_source_checks",
        ["company_source_id"],
    )
    op.create_index("ix_company_source_checks_run_id", "company_source_checks", ["run_id"])

    bind = op.get_bind()
    job_columns = {column["name"] for column in sa.inspect(bind).get_columns("ai_canonical_jobs")}
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
    op.drop_index("ix_ai_canonical_jobs_ingestion_source_id", table_name="ai_canonical_jobs")
    op.drop_index("ix_ai_canonical_jobs_last_seen_at", table_name="ai_canonical_jobs")
    op.drop_constraint(
        "fk_ai_canonical_jobs_ingestion_source", "ai_canonical_jobs", type_="foreignkey"
    )
    op.drop_column("ai_canonical_jobs", "ingestion_source_id")
    op.drop_column("ai_canonical_jobs", "missing_poll_count")
    op.drop_column("ai_canonical_jobs", "last_seen_at")
    op.drop_column("ai_canonical_jobs", "first_seen_at")
    op.drop_index("ix_company_source_checks_run_id", table_name="company_source_checks")
    op.drop_index("ix_company_source_checks_company_source_id", table_name="company_source_checks")
    op.drop_table("company_source_checks")
    op.drop_table("company_watch_runs")
    op.drop_index("ix_company_sources_due", table_name="company_sources")
    op.drop_index("ix_company_sources_company_id", table_name="company_sources")
    op.drop_table("company_sources")
    op.drop_index("ix_company_locations_company_id", table_name="company_locations")
    op.drop_table("company_locations")
    op.drop_index("ix_company_aliases_company_id", table_name="company_aliases")
    op.drop_table("company_aliases")
    op.drop_table("company_intelligence")
