"""cves.fixed_versions, cves.workaround_url, items.action

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-27 22:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('cves', sa.Column('fixed_versions', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('cves', sa.Column('workaround_url', sa.Text(), nullable=True))
    op.add_column('items', sa.Column('action', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'action')
    op.drop_column('cves', 'workaround_url')
    op.drop_column('cves', 'fixed_versions')
