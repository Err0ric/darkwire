"""items.changed_at: last time anything on the row changed (live updates)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-28 00:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'items',
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_items_changed_at', 'items', ['changed_at'])


def downgrade() -> None:
    op.drop_index('ix_items_changed_at', table_name='items')
    op.drop_column('items', 'changed_at')
