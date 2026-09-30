"""items.summary_sources, items.summarized_at: a row's summary is written again when sources join

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("summary_sources", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("summarized_at", sa.DateTime(timezone=True), nullable=True))
    # Rows summarized (or declined) before: as of now, with the sources they have, so they are
    # written again only when a new source joins.
    op.execute("""
        UPDATE items SET summarized_at = now(),
               summary_sources = (SELECT count(*) FROM item_sources s WHERE s.item_id = items.id)
        WHERE summary IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("items", "summarized_at")
    op.drop_column("items", "summary_sources")
