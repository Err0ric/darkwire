"""board_events: what the board just did, for the landing's activity log

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-28 02:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'board_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('detail', sa.Text(), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_board_events_at', 'board_events', ['at'])


def downgrade() -> None:
    op.drop_index('ix_board_events_at', table_name='board_events')
    op.drop_table('board_events')
