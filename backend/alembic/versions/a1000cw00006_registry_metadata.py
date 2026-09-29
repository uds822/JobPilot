"""Preserve careers links and source provenance without duplicating employer identity."""

from alembic import op
import sqlalchemy as sa

revision = "a1000cw00006"
down_revision = "a1000cw00005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("company_intelligence", sa.Column("careers_url", sa.Text(), nullable=True))
    op.add_column("company_sources", sa.Column("evidence_url", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("company_sources", "evidence_url")
    op.drop_column("company_intelligence", "careers_url")
