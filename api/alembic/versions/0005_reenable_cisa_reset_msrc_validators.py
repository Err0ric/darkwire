"""re-enable CISA advisories, clear MSRC conditional-GET validators

CISA's 403 was local-network blocking, not fingerprinting: Railway fetches it fine.
MSRC's ETag / Last-Modified were saved while it was a main feed, so after it became
enrichment the feed kept answering 304 and msrc_updates never filled. Clearing them
forces one full fetch.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-27 02:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MSRC = 'https://api.msrc.microsoft.com/update-guide/rss'
CISA = 'https://www.cisa.gov/cybersecurity-advisories/all.xml'


def upgrade() -> None:
    op.execute(sa.text("UPDATE sources SET enabled = true, health = 'unknown' WHERE feed_url = :u").bindparams(u=CISA))
    op.execute(sa.text("UPDATE sources SET etag = NULL, last_modified = NULL WHERE feed_url = :u").bindparams(u=MSRC))


def downgrade() -> None:
    op.execute(sa.text("UPDATE sources SET enabled = false, health = 'disabled', last_error = NULL "
                       "WHERE feed_url = :u").bindparams(u=CISA))
