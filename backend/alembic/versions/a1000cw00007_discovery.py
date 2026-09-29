"""Durable discovery, source ownership and scoped inventory observations."""

from alembic import op
import sqlalchemy as sa

revision = "a1000cw00007"
down_revision = "a1000cw00006"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("discovery_status", sa.String(30), nullable=False, server_default="discovery_pending"),
        sa.Column("discovery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_discovery_at", sa.DateTime()),
        sa.Column("next_discovery_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')")),
        sa.Column("discovery_error", sa.Text()),
        sa.Column("discovery_claim_token", sa.String(36)),
        sa.Column("discovery_claimed_until", sa.DateTime()),
    ):
        op.add_column("company_intelligence", column)
    op.create_index("ix_company_discovery_due", "company_intelligence", ["is_active", "next_discovery_at", "discovery_claimed_until"])
    for column in (
        sa.Column("canonical_identity", sa.String(300)),
        sa.Column("ownership_status", sa.String(30), nullable=False, server_default="registry_trusted"),
        sa.Column("discovery_evidence", sa.JSON()),
        sa.Column("last_observed_at", sa.DateTime()),
        sa.Column("last_complete_scope", sa.String(80)),
    ):
        op.add_column("company_sources", column)
    # Preserve established source/job IDs. Abort on ambiguous legacy identities
    # instead of silently merging boards owned by different employers.
    op.execute("UPDATE company_sources SET canonical_identity = provider || ':' || lower(identifier)")
    op.create_unique_constraint("uq_company_sources_canonical_identity", "company_sources", ["canonical_identity"])
    op.add_column("ai_canonical_jobs", sa.Column("inventory_scope", sa.String(80), nullable=False, server_default="india_technical_v1"))
    op.create_table(
        "company_discovery_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("evidence", sa.JSON()),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_company_discovery_attempts_company_id", "company_discovery_attempts", ["company_id"])


def downgrade():
    op.drop_table("company_discovery_attempts")
    op.drop_column("ai_canonical_jobs", "inventory_scope")
    op.drop_constraint("uq_company_sources_canonical_identity", "company_sources", type_="unique")
    for name in ("canonical_identity", "ownership_status", "discovery_evidence", "last_observed_at", "last_complete_scope"):
        op.drop_column("company_sources", name)
    op.drop_index("ix_company_discovery_due", "company_intelligence")
    for name in ("discovery_status", "discovery_attempts", "last_discovery_at", "next_discovery_at", "discovery_error", "discovery_claim_token", "discovery_claimed_until"):
        op.drop_column("company_intelligence", name)
