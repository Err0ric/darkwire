"""item_sources.advisory_read_at / advisory_digest / advisory_rechecked_at: a CISA or vendor
advisory is read once more 24-48h after it was first read (app/advisories.py)

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_sources", sa.Column("advisory_read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("item_sources", sa.Column("advisory_digest", sa.String(64), nullable=True))
    op.add_column("item_sources", sa.Column("advisory_rechecked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("item_sources", "advisory_rechecked_at")
    op.drop_column("item_sources", "advisory_digest")
    op.drop_column("item_sources", "advisory_read_at")
