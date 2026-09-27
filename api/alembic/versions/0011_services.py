"""service_status, service_hours: third-party status pages for the Services widget and /outages

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27 23:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'service_status',
        sa.Column('slug', sa.String(64), primary_key=True),
        sa.Column('state', sa.String(16), nullable=False, server_default='unknown'),
        sa.Column('incident_title', sa.Text(), nullable=True),
        sa.Column('incident_url', sa.Text(), nullable=True),
        sa.Column('incident_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.create_table(
        'service_hours',
        sa.Column('slug', sa.String(64), primary_key=True),
        sa.Column('hour', sa.DateTime(timezone=True), primary_key=True),
        sa.Column('worst', sa.String(16), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('service_hours')
    op.drop_table('service_status')
