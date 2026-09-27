"""MSRC becomes enrichment, CISA disabled, Unit 42 unlinked, ad skip count

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27 00:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MSRC = 'https://api.msrc.microsoft.com/update-guide/rss'
CISA = 'https://www.cisa.gov/cybersecurity-advisories/all.xml'
UNIT42 = 'https://unit42.paloaltonetworks.com/feed/'


def _exec(sql: str, **params) -> None:
    op.execute(sa.text(sql).bindparams(**params))


def upgrade() -> None:
    # New enum values must be committed before they can be used.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE stream ADD VALUE IF NOT EXISTS 'enrichment'")
        op.execute("ALTER TYPE health ADD VALUE IF NOT EXISTS 'disabled'")

    op.create_table('msrc_updates',
    sa.Column('cve_id', sa.String(length=32), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('revision_note', sa.Text(), nullable=True),
    sa.Column('revised_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('product', sa.String(length=255), nullable=True),
    sa.Column('severity', sa.String(length=32), nullable=True),
    sa.Column('exploited', sa.Boolean(), nullable=True),
    sa.Column('publicly_disclosed', sa.Boolean(), nullable=True),
    sa.Column('release', sa.String(length=16), nullable=True),
    sa.Column('kbs', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('fixed_builds', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('details_fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('cve_id')
    )
    op.add_column('sync_runs', sa.Column('skipped_ads', sa.Integer(), server_default='0', nullable=False))

    # MSRC: enrichment only. Remove its articles, drop rows left empty, and re-point
    # rows whose primary was an MSRC article at their earliest remaining source.
    _exec("UPDATE sources SET stream = 'enrichment' WHERE feed_url = :u", u=MSRC)
    _exec("DELETE FROM item_sources WHERE source_id IN (SELECT id FROM sources WHERE feed_url = :u)", u=MSRC)
    op.execute("DELETE FROM items i WHERE NOT EXISTS (SELECT 1 FROM item_sources x WHERE x.item_id = i.id)")
    op.execute("""
        UPDATE items i SET primary_url = x.url, headline = x.title
        FROM (SELECT DISTINCT ON (item_id) item_id, url, title FROM item_sources
              ORDER BY item_id, published_at) x
        WHERE x.item_id = i.id
          AND NOT EXISTS (SELECT 1 FROM item_sources y WHERE y.item_id = i.id AND y.url = i.primary_url)
    """)
    op.execute("DELETE FROM cves c WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.cve_id = c.id)")

    _exec("UPDATE sources SET enabled = false, health = 'disabled', last_error = NULL, "
          "consecutive_failures = 0 WHERE feed_url = :u", u=CISA)
    _exec("UPDATE sources SET vendor_id = NULL WHERE feed_url = :u", u=UNIT42)


def downgrade() -> None:
    # Enum values 'enrichment' and 'disabled' stay: Postgres cannot drop enum values.
    # Deleted MSRC rows are not restored.
    _exec("UPDATE sources SET vendor_id = (SELECT id FROM vendors WHERE slug = 'palo-alto-networks') "
          "WHERE feed_url = :u", u=UNIT42)
    _exec("UPDATE sources SET enabled = true, health = 'unknown' WHERE feed_url = :u", u=CISA)
    _exec("UPDATE sources SET stream = 'main' WHERE feed_url = :u", u=MSRC)
    op.drop_column('sync_runs', 'skipped_ads')
    op.drop_table('msrc_updates')
