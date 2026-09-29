"""Backfill source ingestion freshness from canonical inventory.

Revision ID: a1000cw00005
Revises: a1000cw00004
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a1000cw00005"
down_revision: Union[str, Sequence[str], None] = "a1000cw00004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing inventory predates the source-level ingestion timestamp. Its
    # latest observed posting is the strongest truthful backfill available.
    op.execute(
        """
        UPDATE company_sources AS source
        SET last_ingested_at = inventory.last_seen_at
        FROM (
            SELECT ingestion_source_id, max(last_seen_at) AS last_seen_at
            FROM ai_canonical_jobs
            WHERE ingestion_source_id IS NOT NULL
            GROUP BY ingestion_source_id
        ) AS inventory
        WHERE source.id = inventory.ingestion_source_id
          AND source.last_ingested_at IS NULL
        """
    )


def downgrade() -> None:
    # A data backfill cannot be safely distinguished from later real polls.
    pass
