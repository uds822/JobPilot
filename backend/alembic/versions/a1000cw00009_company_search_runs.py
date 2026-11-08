"""Scope search runs to general discovery or one registered company.

Revision ID: a1000cw00009
Revises: a1000cw00008
"""

from alembic import op
import sqlalchemy as sa


revision = "a1000cw00009"
down_revision = "a1000cw00008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("search_runs", sa.Column("search_scope", sa.String(20), nullable=False, server_default="general"))
    op.add_column("search_runs", sa.Column("company_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_search_runs_company_id", "search_runs", "companies", ["company_id"], ["id"])
    op.create_index("ix_search_runs_company_id", "search_runs", ["company_id"])


def downgrade():
    op.drop_index("ix_search_runs_company_id", table_name="search_runs")
    op.drop_constraint("fk_search_runs_company_id", "search_runs", type_="foreignkey")
    op.drop_column("search_runs", "company_id")
    op.drop_column("search_runs", "search_scope")
