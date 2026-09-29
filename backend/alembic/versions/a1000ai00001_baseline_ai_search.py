"""Baseline AI job-search tables for migration-managed schema changes.

Revision ID: a1000ai00001
Revises: b81f3c7e91d0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1000ai00001"
down_revision: Union[str, Sequence[str], None] = "b81f3c7e91d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_if_missing(name: str, *items) -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(name):
        op.create_table(name, *items)


def upgrade() -> None:
    _create_if_missing(
        "ai_canonical_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("remote", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("salary_min", sa.Float()),
        sa.Column("salary_max", sa.Float()),
        sa.Column("salary_currency", sa.String(10)),
        sa.Column("salary_interval", sa.String(20)),
        sa.Column("salary_source", sa.String(50)),
        sa.Column("apply_url", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("posted_date", sa.DateTime()),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime()),
        sa.Column("verification_method", sa.String(50)),
        sa.UniqueConstraint("source", "external_id", name="uq_ai_jobs_source_external_id"),
    )
    _create_if_missing(
        "company_profiles_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("company_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("salary_estimates", sa.JSON()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_if_missing(
        "user_resume_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("raw_resume_text", sa.Text()),
        sa.Column("parsed_profile", sa.JSON(), nullable=False),
        sa.Column("user_preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_if_missing(
        "search_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "profile_version_id",
            sa.Integer(),
            sa.ForeignKey("user_resume_profiles.id"),
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("error_message", sa.Text()),
        sa.Column("jobs_fetched", sa.Integer(), nullable=False),
        sa.Column("jobs_after_dedupe", sa.Integer(), nullable=False),
        sa.Column("jobs_after_validity", sa.Integer(), nullable=False),
        sa.Column("jobs_after_hard_filters", sa.Integer(), nullable=False),
        sa.Column("jobs_scored", sa.Integer(), nullable=False),
        sa.Column("jobs_returned", sa.Integer(), nullable=False),
    )
    _create_if_missing(
        "ai_job_matches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("search_run_id", sa.Integer(), sa.ForeignKey("search_runs.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "profile_version_id",
            sa.Integer(),
            sa.ForeignKey("user_resume_profiles.id"),
        ),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("ai_canonical_jobs.id"), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("match_level", sa.String(30), nullable=False),
        sa.Column("callback_likelihood", sa.String(20), nullable=False),
        sa.Column("match_reasoning", sa.Text()),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column("skills_overlap", sa.Float(), nullable=False),
        sa.Column("experience_fit", sa.Float(), nullable=False),
        sa.Column("role_similarity", sa.Float(), nullable=False),
        sa.Column("location_fit", sa.Float(), nullable=False),
        sa.Column("industry_fit", sa.Float(), nullable=False),
        sa.Column("company_type_fit", sa.Float(), nullable=False),
        sa.Column("posting_freshness", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    bind = op.get_bind()
    indexes = (
        ("ix_ai_canonical_jobs_job_hash", "ai_canonical_jobs", ["job_hash"], False),
        ("ix_ai_canonical_jobs_source", "ai_canonical_jobs", ["source"], False),
        ("ix_ai_canonical_jobs_title", "ai_canonical_jobs", ["title"], False),
        ("ix_ai_canonical_jobs_company", "ai_canonical_jobs", ["company"], False),
        ("ix_company_profiles_cache_company_name", "company_profiles_cache", ["company_name"], True),
        ("ix_user_resume_profiles_user_id", "user_resume_profiles", ["user_id"], False),
        ("ix_search_runs_user_id", "search_runs", ["user_id"], False),
        ("ix_ai_job_matches_search_run_id", "ai_job_matches", ["search_run_id"], False),
        ("ix_ai_job_matches_user_id", "ai_job_matches", ["user_id"], False),
        ("ix_ai_job_matches_job_id", "ai_job_matches", ["job_id"], False),
    )
    existing_indexes = {
        (table, index["name"])
        for table in (
            "ai_canonical_jobs",
            "company_profiles_cache",
            "user_resume_profiles",
            "search_runs",
            "ai_job_matches",
        )
        for index in sa.inspect(bind).get_indexes(table)
    }
    for name, table, columns, unique in indexes:
        if (table, name) not in existing_indexes:
            op.create_index(name, table, columns, unique=unique)


def downgrade() -> None:
    # This is a compatibility baseline: these tables may predate Alembic and
    # may contain production data, so the baseline deliberately never drops them.
    pass
