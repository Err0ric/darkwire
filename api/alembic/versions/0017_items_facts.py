"""items.facts: what the articles state, read with the summary (app/facts.py)

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL: not read yet. {}: read, nothing verified. Otherwise the verified facts with quotes.
    op.add_column("items", sa.Column("facts", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "facts")
