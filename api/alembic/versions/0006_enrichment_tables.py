"""enrichment: item_cves, kev_entries, job_state, derived cve columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27 12:00:00
"""
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CVE_RE = re.compile(r"\bCVE-(\d{4})-(\d{4,7})\b", re.IGNORECASE)
patch_status = postgresql.ENUM('patched', 'no_fix', 'workaround', 'unverified', name='patch_status', create_type=False)


def upgrade() -> None:
    op.add_column('cves', sa.Column('nvd_status', sa.String(length=32), nullable=True))
    op.add_column('cves', sa.Column('affected', sa.Text(), nullable=True))
    op.add_column('cves', sa.Column('patch_status', patch_status, nullable=True))
    op.add_column('cves', sa.Column('patch_url', sa.Text(), nullable=True))

    op.create_table('item_cves',
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('cve_id', sa.String(length=32), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['cve_id'], ['cves.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', 'cve_id')
    )
    op.create_index(op.f('ix_item_cves_cve_id'), 'item_cves', ['cve_id'], unique=False)

    op.create_table('kev_entries',
    sa.Column('cve_id', sa.String(length=32), nullable=False),
    sa.Column('vendor', sa.String(length=255), nullable=True),
    sa.Column('product', sa.String(length=255), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('date_added', sa.Date(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('ransomware', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('cve_id')
    )
    op.create_index(op.f('ix_kev_entries_date_added'), 'kev_entries', ['date_added'], unique=False)

    op.create_table('job_state',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )

    # Backfill item_cves: the row's current CVE first, then every CVE its articles'
    # titles and first paragraphs mention, in order of appearance.
    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT i.id, i.cve_id,
               string_agg(coalesce(s.title, '') || ' ' || coalesce(s.excerpt, ''), ' ' ORDER BY s.published_at)
        FROM items i JOIN item_sources s ON s.item_id = i.id
        WHERE i.stream = 'main'
        GROUP BY i.id, i.cve_id
    """)).all()
    for item_id, cve_id, text in rows:
        found: list[str] = [cve_id] if cve_id else []
        for year, num in CVE_RE.findall(text or ''):
            c = f'CVE-{year}-{num}'
            if c not in found:
                found.append(c)
        for pos, c in enumerate(found):
            conn.execute(sa.text("INSERT INTO cves (id) VALUES (:c) ON CONFLICT DO NOTHING"), {'c': c})
            conn.execute(
                sa.text("INSERT INTO item_cves (item_id, cve_id, position) VALUES (:i, :c, :p) ON CONFLICT DO NOTHING"),
                {'i': item_id, 'c': c, 'p': pos},
            )


def downgrade() -> None:
    op.drop_table('job_state')
    op.drop_index(op.f('ix_kev_entries_date_added'), table_name='kev_entries')
    op.drop_table('kev_entries')
    op.drop_index(op.f('ix_item_cves_cve_id'), table_name='item_cves')
    op.drop_table('item_cves')
    op.drop_column('cves', 'patch_url')
    op.drop_column('cves', 'patch_status')
    op.drop_column('cves', 'affected')
    op.drop_column('cves', 'nvd_status')
