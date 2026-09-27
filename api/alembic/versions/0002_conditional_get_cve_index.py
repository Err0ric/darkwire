"""conditional GET validators on sources, non-unique items.cve_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 22:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('sources', sa.Column('etag', sa.Text(), nullable=True))
    op.add_column('sources', sa.Column('last_modified', sa.Text(), nullable=True))
    op.drop_constraint('items_cve_id_key', 'items', type_='unique')
    op.create_index(op.f('ix_items_cve_id'), 'items', ['cve_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_items_cve_id'), table_name='items')
    op.create_unique_constraint('items_cve_id_key', 'items', ['cve_id'])
    op.drop_column('sources', 'last_modified')
    op.drop_column('sources', 'etag')
