"""Preserve posting evidence and per-user experience decisions.

Revision ID: a1000cw00008
Revises: a1000cw00007
"""

from alembic import op
import sqlalchemy as sa


revision = "a1000cw00008"
down_revision = "a1000cw00007"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("description_excerpt", sa.Text()),
        sa.Column("description_completeness", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("description_enrichment_checked_at", sa.DateTime()),
        sa.Column("description_enrichment_status", sa.String(20)),
        sa.Column("required_experience_min", sa.Float()),
        sa.Column("required_experience_max", sa.Float()),
        sa.Column("experience_source", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("experience_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("experience_evidence", sa.Text()),
        sa.Column("seniority_level", sa.String(20)),
        sa.Column("seniority_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("experience_parse_version", sa.Integer(), nullable=False, server_default="0"),
    ):
        op.add_column("ai_canonical_jobs", column)
    op.execute(
        "UPDATE ai_canonical_jobs SET description_completeness = 'snippet', "
        "description_excerpt = description WHERE source = 'adzuna' AND description IS NOT NULL"
    )
    for column in (
        sa.Column("experience_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("experience_reason", sa.Text()),
        sa.Column("seniority_conflict", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        op.add_column("ai_job_matches", column)


def downgrade():
    for name in ("seniority_conflict", "experience_reason", "experience_status"):
        op.drop_column("ai_job_matches", name)
    for name in (
        "experience_parse_version", "seniority_confidence", "seniority_level",
        "experience_evidence", "experience_confidence", "experience_source",
        "required_experience_max", "required_experience_min",
        "description_enrichment_status", "description_enrichment_checked_at",
        "description_completeness", "description_excerpt",
    ):
        op.drop_column("ai_canonical_jobs", name)
