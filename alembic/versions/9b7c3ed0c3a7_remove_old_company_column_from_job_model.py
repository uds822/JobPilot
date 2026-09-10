"""remove old company column from job model

Revision ID: 9b7c3ed0c3a7
Revises: 7715d9b8fdf9
Create Date: 2026-09-01 19:51:41.812196

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9b7c3ed0c3a7"
down_revision: Union[str, Sequence[str], None] = "7715d9b8fdf9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Safe idempotent migration: this column may already have been removed by an earlier migration.
    if _column_exists("jobs", "company"):
        op.drop_column("jobs", "company")


def downgrade() -> None:
    # Re-add the column if it is missing.
    if not _column_exists("jobs", "company"):
        op.add_column("jobs", sa.Column("company", sa.VARCHAR(), nullable=True))
