"""create companies table

Revision ID: 10bcdd303f4d
Revises: 3d72b4b982ea
Create Date: 2026-08-28 01:33:05.331549

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "10bcdd303f4d"
down_revision: Union[str, Sequence[str], None] = "3d72b4b982ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 1. Create Company records for old company names
    op.execute("""
        INSERT INTO companies (name)
        SELECT DISTINCT company
        FROM jobs
        WHERE company IS NOT NULL
        AND NOT EXISTS (
            SELECT 1
            FROM companies c
            WHERE c.name = jobs.company
        )
    """)

    # 2. Add company_id temporarily as nullable
    op.add_column("jobs", sa.Column("company_id", sa.Integer(), nullable=True))

    # 3. Copy the correct company ID into each job
    op.execute("""
        UPDATE jobs
        SET company_id = companies.id
        FROM companies
        WHERE jobs.company = companies.name
    """)

    # 4. Now every job should have a company_id
    op.alter_column("jobs", "company_id", nullable=False)

    # 5. Create the Foreign Key
    op.create_foreign_key(
        "fk_jobs_company_id", "jobs", "companies", ["company_id"], ["id"]
    )

    # 6. Remove the old company string
    op.drop_column("jobs", "company")


def downgrade() -> None:

    # 1. Restore old company column
    op.add_column("jobs", sa.Column("company", sa.String(length=200), nullable=True))

    # 2. Restore company names from companies table
    op.execute("""
        UPDATE jobs
        SET company = companies.name
        FROM companies
        WHERE jobs.company_id = companies.id
    """)

    # 3. Remove Foreign Key
    op.drop_constraint("fk_jobs_company_id", "jobs", type_="foreignkey")

    # 4. Remove company_id
    op.drop_column("jobs", "company_id")

    # 5. Remove the table created by this revision
    op.drop_table("companies")
