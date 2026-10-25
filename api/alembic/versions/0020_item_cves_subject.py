"""item_cves.subject: the CVE was a subject CVE of one of the row's articles when linked, kept
because the fetched article it came from is never stored (app/article_cves.py)

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_cves", sa.Column("subject", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("item_cves", "subject")
