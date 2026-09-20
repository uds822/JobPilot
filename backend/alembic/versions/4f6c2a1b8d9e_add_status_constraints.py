"""add status check constraints

Revision ID: 4f6c2a1b8d9e
Revises: 27af957896f1
Create Date: 2026-09-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f6c2a1b8d9e"
down_revision: Union[str, Sequence[str], None] = "27af957896f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_jobs_status_valid",
        "jobs",
        "status IN ('SAVED', 'APPLIED', 'INTERVIEWING', 'OFFERED', 'REJECTED')",
    )
    op.create_check_constraint(
        "ck_applications_status_valid",
        "applications",
        "status IN ('APPLIED', 'INTERVIEWING', 'OFFERED', 'REJECTED', 'WITHDRAWN')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_applications_status_valid", "applications", type_="check")
    op.drop_constraint("ck_jobs_status_valid", "jobs", type_="check")
