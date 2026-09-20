"""add applications composite index for user status filtering and sorting

Revision ID: b81f3c7e91d0
Revises: 4f6c2a1b8d9e
Create Date: 2026-09-21 03:07:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b81f3c7e91d0"
down_revision: Union[str, Sequence[str], None] = "4f6c2a1b8d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_applications_user_status_applied_at",
        "applications",
        ["user_id", "status", "applied_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_applications_user_status_applied_at", table_name="applications")
