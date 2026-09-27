"""drop "Unit 42" as a Palo Alto Networks alias

A vendor's research blog is not news about that vendor's products.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27 01:00:00
"""
from collections.abc import Sequence

from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE vendors SET aliases = array_remove(aliases, 'Unit 42') WHERE slug = 'palo-alto-networks'")


def downgrade() -> None:
    op.execute("UPDATE vendors SET aliases = array_append(aliases, 'Unit 42') "
               "WHERE slug = 'palo-alto-networks' AND NOT 'Unit 42' = ANY(aliases)")
