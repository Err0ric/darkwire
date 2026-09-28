"""items.topic: the Elsewhere relevance topic (privacy, surveillance, policy, ...) or off-topic

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-28 01:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('items', sa.Column('topic', sa.String(length=24), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'topic')
