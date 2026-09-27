"""service_incidents: third-party incidents of the last days, for the /services panel

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-28 01:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'service_incidents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('slug', sa.String(length=64), nullable=False),
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('state', sa.String(length=16), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('slug', 'key', name='uq_service_incidents_slug_key'),
    )
    op.create_index('ix_service_incidents_slug', 'service_incidents', ['slug'])
    op.create_index('ix_service_incidents_started_at', 'service_incidents', ['started_at'])


def downgrade() -> None:
    op.drop_index('ix_service_incidents_started_at', table_name='service_incidents')
    op.drop_index('ix_service_incidents_slug', table_name='service_incidents')
    op.drop_table('service_incidents')
