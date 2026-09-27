"""merge rows that share a CVE, using the live clustering rule

Rows created before clustering looked at every CVE (item_cves) can duplicate each other.
Replays ingest's rule over existing rows, oldest first: a row folds into an earlier row
when they share any CVE and its first article was published within 48h of the earlier
row's last_event_at. The surviving row takes every source and CVE. Data-only; no downgrade.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-27 18:00:00
"""
import logging
from collections.abc import Sequence
from datetime import timedelta

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WINDOW = timedelta(hours=48)
log = logging.getLogger('alembic.runtime.migration')


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT i.id, i.last_event_at, i.last_event_kind, i.first_seen_at, i.vendor_id, i.category::text,
               i.summary, i.kev, i.cvss,
               (SELECT min(published_at) FROM item_sources s WHERE s.item_id = i.id) AS first_pub
        FROM items i WHERE i.stream = 'main'
    """)).mappings().all()
    cves: dict[int, set[str]] = {}
    for item_id, cve_id in conn.execute(sa.text("SELECT item_id, cve_id FROM item_cves")).all():
        cves.setdefault(item_id, set()).add(cve_id)

    items = {r['id']: dict(r) for r in rows if cves.get(r['id'])}
    order = sorted(items.values(), key=lambda r: (r['first_pub'] or r['last_event_at'], r['id']))
    survivors: list[dict] = []
    merged = 0
    for n in order:
        pub = n['first_pub'] or n['last_event_at']
        candidates = [
            o for o in survivors
            if cves[o['id']] & cves[n['id']] and abs(pub - o['last_event_at']) <= WINDOW
        ]
        if not candidates:
            survivors.append(n)
            continue
        o = max(candidates, key=lambda r: r['last_event_at'])  # ingest picks the latest match
        _merge(conn, o, n, pub)
        cves[o['id']] |= cves.pop(n['id'])
        merged += 1

    log.info('merged %d duplicate rows', merged)


def _merge(conn, o: dict, n: dict, n_pub) -> None:
    oid, nid = o['id'], n['id']
    conn.execute(sa.text("UPDATE item_sources SET item_id = :o WHERE item_id = :n"), {'o': oid, 'n': nid})
    conn.execute(sa.text("""
        INSERT INTO item_cves (item_id, cve_id, position)
        SELECT :o, cve_id, (SELECT coalesce(max(position), -1) + 1 FROM item_cves WHERE item_id = :o) + position
        FROM item_cves WHERE item_id = :n
        ON CONFLICT DO NOTHING
    """), {'o': oid, 'n': nid})

    # Timing: a publish-only row moves to the earliest article, as ingest does; a real
    # event (KEV added, score change) on either row is kept.
    event, kind = o['last_event_at'], o['last_event_kind']
    if kind == 'published' and n_pub < event:
        event = n_pub
    if n['last_event_kind'] not in (None, 'published') and n['last_event_at'] > event:
        event, kind = n['last_event_at'], n['last_event_kind']

    # Primary source: a vendor feed wins, else the earliest article.
    primary = conn.execute(sa.text("""
        SELECT s.url, s.title, src.vendor_id FROM item_sources s JOIN sources src ON src.id = s.source_id
        WHERE s.item_id = :o
        ORDER BY (src.vendor_id IS NULL), s.published_at NULLS LAST, s.id LIMIT 1
    """), {'o': oid}).mappings().one()

    scores = [x for x in (o['cvss'], n['cvss']) if x is not None]
    values = {
        'o': oid,
        'headline': primary['title'],
        'url': primary['url'],
        'vendor': primary['vendor_id'] or o['vendor_id'] or n['vendor_id'],
        'category': n['category'] if o['category'] == 'news' else o['category'],
        'summary': o['summary'] or n['summary'],
        # Kept at the pair's max so the next roll-up does not see a "change" and resurface it.
        'kev': bool(o['kev'] or n['kev']),
        'cvss': max(scores) if scores else None,
        'event': event,
        'kind': kind,
        'first_seen': min(o['first_seen_at'], n['first_seen_at']),
    }
    conn.execute(sa.text("""
        UPDATE items SET headline = :headline, primary_url = :url, vendor_id = :vendor,
               category = CAST(:category AS category), summary = :summary, kev = :kev, cvss = :cvss,
               last_event_at = :event, last_event_kind = :kind, first_seen_at = :first_seen
        WHERE id = :o
    """), values)
    conn.execute(sa.text("DELETE FROM items WHERE id = :n"), {'n': nid})

    o.update(last_event_at=event, last_event_kind=kind, vendor_id=values['vendor'], category=values['category'],
             summary=values['summary'], kev=values['kev'], cvss=values['cvss'], first_seen_at=values['first_seen'])


def downgrade() -> None:
    pass  # merged rows are not split back apart
