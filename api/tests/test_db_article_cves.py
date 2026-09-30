"""The live path of app/article_cves.py against a real Postgres, in a throwaway database.

Each run creates its own database (darkwire_test_<random>) on the local server, builds the schema
from the models, and drops the database in tearDown whatever the code under test committed. It
never touches the app's database, and refuses any host but localhost. Skipped when no local
Postgres answers (docker compose up -d).

    cd api && python -m unittest discover -s tests
    TEST_PG_ADMIN_URL=postgresql://user:pass@localhost:5432/postgres   # optional
"""

import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app import article_cves, enrich
from app.models import Base, Category, Cve, Item, ItemCve, ItemSource, KevEntry, Source, Stream

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL", "postgresql://darkwire:darkwire@localhost:5432/postgres")


def _async(url: str) -> str:
    return "postgresql+asyncpg://" + url.split("://", 1)[1]


class LivePath(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(ADMIN_URL).hostname not in ("localhost", "127.0.0.1"):
            self.skipTest("TEST_PG_ADMIN_URL must point at localhost")
        self.name = f"darkwire_test_{uuid.uuid4().hex[:12]}"
        self.admin = create_async_engine(_async(ADMIN_URL), isolation_level="AUTOCOMMIT")
        try:
            async with self.admin.connect() as c:
                await c.execute(text(f'CREATE DATABASE "{self.name}"'))
        except Exception as e:  # no local Postgres
            await self.admin.dispose()
            self.skipTest(f"no local Postgres: {e}")
        self.addAsyncCleanup(self._drop)
        base = ADMIN_URL.rsplit("/", 1)[0]
        self.engine = create_async_engine(_async(f"{base}/{self.name}"))
        async with self.engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def _drop(self):
        # Runs even when the test failed or the code under test committed.
        if getattr(self, "engine", None):
            await self.engine.dispose()
        async with self.admin.connect() as c:
            await c.execute(text(f'DROP DATABASE IF EXISTS "{self.name}" WITH (FORCE)'))
        await self.admin.dispose()

    async def _row(self, s, source, headline, at, cves=(), excerpt=None):
        for c in cves:
            await s.merge(Cve(id=c))
        await s.flush()
        item = Item(stream=Stream.main, headline=headline, primary_url=f"https://test.invalid/{uuid.uuid4().hex}",
                    category=Category.news, last_event_at=at, last_event_kind="published", cve_id=cves[0] if cves else None)
        s.add(item)
        await s.flush()
        s.add(ItemSource(item_id=item.id, source_id=source.id, url=item.primary_url, title=headline, excerpt=excerpt, published_at=at))
        for i, c in enumerate(cves):
            s.add(ItemCve(item_id=item.id, cve_id=c, position=i))
        await s.flush()
        return item

    async def _load(self, s, ids):
        return list((await s.scalars(select(Item).where(Item.id.in_(ids)).options(selectinload(Item.sources)))).all())

    async def test_live_path_rules(self):
        now = datetime.now(UTC)
        t0 = now - timedelta(days=1)
        async with self.Session() as s:
            src = Source(name="BleepingComputer", feed_url="https://test.invalid/feed", stream=Stream.main)
            s.add(src)
            await s.flush()
            citrix = await self._row(s, src, "Two Citrix zero-days exploited", t0, ["CVE-2026-88771"],
                                     excerpt="Attackers exploit CVE-2026-88771 in NetScaler.")
            # An old CVE the next article mentions for context (NVD date stored: no network lookup).
            s.add(Cve(id="CVE-2024-3400", published_at=datetime(2024, 4, 12, tzinfo=UTC)))
            later = await self._row(s, src, "CISA orders feds to patch exploited Citrix flaws", t0 + timedelta(hours=22))
            recap = await self._row(s, src, "Weekly Recap: Citrix Exploits", t0 + timedelta(hours=23))
            # A multi-story article: SharePoint and MikroTik CVEs (vendors from the KEV catalog).
            mikrotik = await self._row(s, src, "MikroTrick chain takes over MikroTik routers", t0, ["CVE-2026-67279"])
            multi = await self._row(s, src, "SharePoint RCE and MikroTik RouterOS flaws exploited", t0 + timedelta(hours=5))
            s.add_all([
                KevEntry(cve_id="CVE-2026-65660", vendor="Microsoft", product="SharePoint", date_added=now.date()),
                KevEntry(cve_id="CVE-2026-67279", vendor="MikroTik", product="RouterOS", date_added=now.date()),
            ])
            await s.commit()
            ids = {k: v.id for k, v in dict(citrix=citrix, later=later, recap=recap, mikrotik=mikrotik, multi=multi).items()}

        async with self.Session() as s:
            items = await self._load(s, [ids["later"], ids["recap"], ids["multi"]])
            fetched = {}
            for i in items:
                body = {
                    ids["later"]: (
                        "Agencies must patch CVE-2026-88771 by Wednesday.\nThe order covers NetScaler ADC.\n"
                        "It recalls CVE-2024-3400, exploited last year."  # third paragraph, once: context
                    ),
                    ids["recap"]: "This week: CVE-2026-88771 in Citrix.",
                    ids["multi"]: "Attackers exploit CVE-2026-65660 in SharePoint and CVE-2026-67279 in RouterOS.",
                }[i.id]
                fetched[i.id] = {i.sources[0].id: body}
            await article_cves.after_fetch(s, items, fetched)  # commits

        async with self.Session() as s:
            left = set(await s.scalars(select(Item.id).where(Item.id.in_(ids.values()))))
            held = {}
            for k, v in ids.items():
                held[k] = set(await s.scalars(select(ItemCve.cve_id).where(ItemCve.item_id == v)))
            # The later Citrix story merged into the earlier row; its old context CVE was dropped.
            self.assertNotIn(ids["later"], left)
            self.assertEqual(held["citrix"], {"CVE-2026-88771"})
            # The recap gained nothing and merged nowhere.
            self.assertIn(ids["recap"], left)
            self.assertEqual(held["recap"], set())
            # The multi-story row got both CVEs and did not merge into the MikroTik row.
            self.assertIn(ids["multi"], left)
            self.assertEqual(held["multi"], {"CVE-2026-65660", "CVE-2026-67279"})
            self.assertEqual(held["mikrotik"], {"CVE-2026-67279"})

    async def test_a_new_row_pins_its_highest_scored_subject_cve(self):
        from app import cve_facts

        async with self.Session() as s:
            s.add_all([Cve(id="CVE-2026-10001", base_score=5.0), Cve(id="CVE-2026-10002", base_score=9.1),
                       Cve(id="CVE-2026-10003", base_score=10.0)])
            await s.commit()
            cves = ["CVE-2026-10001", "CVE-2026-10002", "CVE-2026-10003"]
            # 10003 scores highest but is context; of the subject CVEs 10002 wins over first-mentioned 10001.
            self.assertEqual(await cve_facts.pick_pinned(s, cves, {"CVE-2026-10001", "CVE-2026-10002"}), "CVE-2026-10002")
            # Unscored subject CVEs: the first mentioned.
            self.assertEqual(await cve_facts.pick_pinned(s, ["CVE-2026-20001", "CVE-2026-20002"], {"CVE-2026-20002", "CVE-2026-20001"}), "CVE-2026-20001")

    async def test_facts_report_logs_counts_poc_quotes_and_sources(self):
        from app import facts_backfill

        now = datetime.now(UTC)
        async with self.Session() as s:
            src = Source(name="BleepingComputer", feed_url="https://test.invalid/bc", stream=Stream.main)
            s.add(src)
            await s.flush()
            poc = await self._row(s, src, "Exploit released for Ubuntu flaw", now, excerpt="A proof-of-concept exploit is now public on GitHub.")
            other = await self._row(s, src, "Kiteworks fixes flaw", now)
            weak = await self._row(s, src, "Spectre v2 variant", now)
            await s.commit()
            state = {"results": {
                str(poc.id): {"public_poc": {"quote": "A proof-of-concept exploit is now public on GitHub."}},
                str(other.id): {"fixed": {"version": "9.5.1", "quote": "Kiteworks released version 9.5.1 to fix it."}},
                str(weak.id): {"public_poc": {"quote": "The researchers' proof-of-concept showed that entries persist."},
                               "fixed": {"version": "Linux kernel", "quote": "Fixes have already been merged into the Linux kernel."}},
            }}
            with self.assertLogs("app.facts_backfill", level="INFO") as logs:
                await facts_backfill._report(s, state)
        text = "\n".join(logs.output)
        self.assertIn("2 rows gain facts: POC 1, affected 0, fixed 1", text)
        self.assertIn("removed by the content rules: fixed 1, public_poc 1", text)
        self.assertIn(f"POC item {poc.id} | public_poc | quote 'A proof-of-concept exploit is now public on GitHub.' | source BleepingComputer", text)
        self.assertIn(f"affected/fixed item {other.id} | fixed = '9.5.1'", text)
        self.assertIn("source fetched article, one of: BleepingComputer", text)
        self.assertEqual(state["results"][str(weak.id)], {})
        self.assertIn("public_poc", state["results_original"][str(weak.id)])

    async def test_live_check_rechecks_summaries_and_logs_fact_quotes(self):
        from app import facts_backfill

        async with self.Session() as s:
            src = Source(name="SecurityWeek", feed_url="https://test.invalid/sw", stream=Stream.main)
            s.add(src)
            await s.flush()
            row = await self._row(s, src, "TeamViewer urges users to patch", datetime.now(UTC))
            row.summary = "TeamViewer fixed two flaws in its remote access client, according to SecurityWeek."
            row.facts = {"fixed": {"version": "15.70", "quote": "TeamViewer says version 15.70 fixes both flaws."}}
            await s.commit()
            with self.assertLogs("app.facts_backfill", level="INFO") as logs:
                await facts_backfill._live_check(s)
        text = "\n".join(logs.output)
        self.assertIn(f"item {row.id}", text)
        self.assertIn("summary passes, unchanged", text)
        self.assertIn("fixed = '15.70' | quote 'TeamViewer says version 15.70 fixes both flaws.'", text)

    async def test_explain_logs_the_qualifying_sentence_per_source(self):
        async with self.Session() as s:
            src = Source(name="The Record", feed_url="https://test.invalid/rec", stream=Stream.main)
            s.add(src)
            await s.flush()
            row = await self._row(s, src, "Attackers exploit Oracle PeopleSoft flaw", datetime.now(UTC), ["CVE-2026-35273"],
                                  excerpt="Attackers are exploiting CVE-2026-35273 in PeopleSoft. More later.")
            await s.commit()
            with self.assertLogs("app.article_cves", level="INFO") as logs:
                await article_cves.explain(s, row.id, "CVE-2026-35273")
                await article_cves.explain(s, 999999, "CVE-2026-35273")
        text = "\n".join(logs.output)
        self.assertIn(f"explain item {row.id} CVE-2026-35273 | Attackers exploit Oracle PeopleSoft flaw", text)
        self.assertIn("The Record: 'Attackers are exploiting CVE-2026-35273 in PeopleSoft.'", text)
        self.assertIn("explain item 999999: gone", text)

    async def test_live_revalidation_removes_failing_facts(self):
        from app import facts_backfill

        async with self.Session() as s:
            src = Source(name="The Hacker News", feed_url="https://test.invalid/thn2", stream=Stream.main)
            s.add(src)
            await s.flush()
            citrix = await self._row(s, src, "Citrix NetScaler CVE-2026-88772 Exploit Details", datetime.now(UTC),
                                     ["CVE-2026-88772", "CVE-2026-88771"])
            citrix.facts = {
                "affected": {"text": "Citrix NetScaler ADC and NetScaler Gateway", "quote": "Citrix NetScaler ADC and NetScaler Gateway contain a flaw."},
                "public_poc": {"quote": "The company released a proof-of-concept (PoC) for CVE-2026-88771"},
            }
            breach = await self._row(s, src, "Pentagon personnel data breach", datetime.now(UTC))
            breach.facts = {"affected": {"text": "2.76 million living individuals", "quote": "the breach impacts 2.76 million living individuals"}}
            await s.commit()
            with self.assertLogs("app.facts_backfill", level="INFO") as logs:
                await facts_backfill._revalidate_live(s)
            ids = (citrix.id, breach.id)
        async with self.Session() as s:
            self.assertEqual(set((await s.get(Item, ids[0])).facts), {"affected"})
            self.assertEqual((await s.get(Item, ids[1])).facts, {})
        text = "\n".join(logs.output)
        self.assertIn(f"item {ids[0]} | removed public_poc (about another CVE (CVE-2026-88771))", text)
        self.assertIn(f"item {ids[1]} | removed affected = '2.76 million living individuals'", text)
        self.assertIn("2 live rows checked, 2 facts removed", text)

    async def test_pinning_rule_dry_run_and_manual_repin(self):
        from app import cve_facts, maintenance
        from app.models import KevEntry

        now = datetime.now(UTC)
        async with self.Session() as s:
            src = Source(name="The Hacker News", feed_url="https://test.invalid/thn3", stream=Stream.main)
            s.add(src)
            await s.flush()
            excerpt = "CVE-2026-86060 and CVE-2026-67279 chain into a takeover. It recalls CVE-2026-67276."
            row = await self._row(s, src, "MikroTrick chain", now, ["CVE-2026-86060", "CVE-2026-67279", "CVE-2026-67276"], excerpt=excerpt)
            (await s.get(Cve, "CVE-2026-86060")).base_score = 9.8
            (await s.get(Cve, "CVE-2026-67279")).base_score = 6.5
            (await s.get(Cve, "CVE-2026-67276")).base_score = 10.0
            s.add(KevEntry(cve_id="CVE-2026-67279", vendor="MikroTik", product="RouterOS", date_added=now.date()))
            await s.commit()
            cves = ["CVE-2026-86060", "CVE-2026-67279", "CVE-2026-67276"]
            subject = {"CVE-2026-86060", "CVE-2026-67279"}
            # KEV-listed subject over the higher score; the 10.0 context CVE is never eligible.
            self.assertEqual(await cve_facts.pick_pinned(s, cves, subject), "CVE-2026-67279")
            # Named in the headline beats KEV.
            self.assertEqual(await cve_facts.pick_pinned(s, cves, subject, "Critical CVE-2026-86060 in RouterOS"), "CVE-2026-86060")
            # The dry run reports the row (displays 86060, the rule picks 67279) and writes nothing.
            with self.assertLogs("app.maintenance", "INFO") as logs:
                self.assertEqual(await maintenance.repin_dry_run(s), {row.id: ("CVE-2026-86060", "CVE-2026-67279")})
            self.assertIn("1 rows would change (STOP: expected 0); nothing written", " ".join(logs.output))
            self.assertEqual((await s.get(Item, row.id)).cve_id, "CVE-2026-86060")
            # Sticky: a roll-up leaves the pin alone.
            await enrich.roll_up(s)
            self.assertEqual((await s.get(Item, row.id)).cve_id, "CVE-2026-86060")
            self.addCleanup(setattr, maintenance, "REPIN_MANUAL", maintenance.REPIN_MANUAL)
            maintenance.REPIN_MANUAL = {row.id: "CVE-2026-67279", 999999: "CVE-2026-67279"}
            await maintenance.repin_manual(s)
        async with self.Session() as s:
            self.assertEqual((await s.get(Item, row.id)).cve_id, "CVE-2026-67279")

    async def test_signed_off_merge(self):
        from app import maintenance

        now = datetime.now(UTC)
        async with self.Session() as s:
            src = Source(name="The Record", feed_url="https://test.invalid/rec2", stream=Stream.main)
            s.add(src)
            await s.flush()
            first = await self._row(s, src, "Attackers exploit PeopleSoft", now - timedelta(hours=10), ["CVE-2026-35273"])
            later = await self._row(s, src, "ShinyHunters PeopleSoft workarounds", now - timedelta(hours=5), ["CVE-2026-35273"])
            await s.commit()
            self.addCleanup(setattr, maintenance, "MERGES", maintenance.MERGES)
            maintenance.MERGES = [(later.id, first.id)]
            await maintenance.merges(s)
        async with self.Session() as s:
            self.assertIsNone(await s.get(Item, later.id))
            srcs = (await s.scalars(select(ItemSource).where(ItemSource.item_id == first.id))).all()
            self.assertEqual(len(srcs), 2)

    async def test_summary_versions_gives_an_ics_row_its_template(self):
        from app import maintenance

        async with self.Session() as s:
            src = Source(name="CISA", feed_url="https://test.invalid/cisa", stream=Stream.main)
            s.add(src)
            await s.flush()
            row = await self._row(s, src, "MikroTik RouterOS", datetime.now(UTC), ["CVE-2026-84411"])
            row.primary_url = "https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-06"
            row.summary = ("MikroTik RouterOS versions before 7.24 contain an integer underflow in the web service. "
                           "MikroTik recommends updating to version 7.23 or later.")
            await s.commit()
            await maintenance.summary_versions(s)
        async with self.Session() as s:
            self.assertEqual((await s.get(Item, row.id)).summary,
                             "CISA industrial control systems advisory for MikroTik RouterOS, covering 1 CVE.")

    async def test_batch_applies_only_when_the_changes_are_exactly_the_signed_off_ones(self):
        from app import facts_backfill

        now = datetime.now(UTC)
        async with self.Session() as s:
            src = Source(name="CISA", feed_url="https://test.invalid/cisa2", stream=Stream.main)
            s.add(src)
            await s.flush()
            good = await self._row(s, src, "Lantronix G520", now)
            plc = await self._row(s, src, "OpenPLC Runtime v3", now)
            await s.commit()
            original = {
                str(good.id): {"fixed": {"version": "2.6.0.7R6", "quote": "fixed in release version 2.6.0.7R6"}},
                str(plc.id): {"fixed": {"version": "OpenPLC v4", "quote": "upgrade to OpenPLC v4"}},
            }
            self.addCleanup(setattr, facts_backfill, "APPLY_IF_ONLY", facts_backfill.APPLY_IF_ONLY)
            # Something else changes too: stop, nothing written.
            facts_backfill.APPLY_IF_ONLY = set()
            state = {"results_original": original, "results": original}
            self.assertFalse(await facts_backfill.report_and_maybe_apply(s, state))
            self.assertIsNone((await s.get(Item, good.id)).facts)
            # Exactly the signed-off change: applied.
            facts_backfill.APPLY_IF_ONLY = {(str(plc.id), "fixed", "removed")}
            state = {"results_original": original, "results": original}
            self.assertTrue(await facts_backfill.report_and_maybe_apply(s, state))
        async with self.Session() as s:
            self.assertEqual((await s.get(Item, good.id)).facts["fixed"]["version"], "2.6.0.7R6")
            self.assertEqual((await s.get(Item, plc.id)).facts, {})

    async def test_summaries_are_written_again_when_sources_join(self):
        import json
        from types import SimpleNamespace
        from unittest import mock

        from app import summaries

        now = datetime.now(UTC)

        def out(text):
            return json.dumps({"summary": text, "facts": {
                "exploited_in_wild": {"stated": False, "quote": None}, "public_poc": {"stated": False, "quote": None},
                "affected": {"text": None, "quote": None}, "fixed": {"version": None, "quote": None}}})

        async with self.Session() as s:
            src = Source(name="BleepingComputer", feed_url="https://test.invalid/bc2", stream=Stream.main)
            s.add(src)
            await s.flush()
            new = await self._row(s, src, "New row", now)
            grew = await self._row(s, src, "Grew row", now)
            s.add(ItemSource(item_id=grew.id, source_id=src.id, url="https://test.invalid/grew2", title="Grew row too", published_at=now))
            grew.summary, grew.summary_sources, grew.summarized_at = "Old summary of the grew row.", 1, now - timedelta(hours=7)
            recent = await self._row(s, src, "Recent row", now)
            s.add(ItemSource(item_id=recent.id, source_id=src.id, url="https://test.invalid/recent2", title="Recent too", published_at=now))
            recent.summary, recent.summary_sources, recent.summarized_at = "Recent summary.", 1, now - timedelta(hours=1)
            fails = await self._row(s, src, "Fails row", now)
            s.add(ItemSource(item_id=fails.id, source_id=src.id, url="https://test.invalid/fails2", title="Fails too", published_at=now))
            fails.summary, fails.summary_sources, fails.summarized_at = "Kept summary of the fails row.", 1, now - timedelta(hours=7)
            await s.commit()
            ids = {"new": new.id, "grew": grew.id, "recent": recent.id, "fails": fails.id}

            answers = {
                ids["new"]: out("Researchers found a flaw in the new row's product that lets attackers read files remotely."),
                ids["grew"]: out("The grew row's product has a flaw attackers exploit to run code; two outlets report active attacks."),
                ids["fails"]: out("SKIP"),
            }
            asked = []

            async def fake_run(session, items, call, label):
                asked.extend(i.id for i in items)
                return [answers.get(i.id) for i in items]

            async def nothing(*a, **k):
                return {} if a and isinstance(a[0], list) else None

            with mock.patch.object(summaries, "get_settings", return_value=SimpleNamespace(anthropic_api_key="test")), \
                 mock.patch.object(summaries, "_run", fake_run), \
                 mock.patch.object(summaries, "_fetch_articles", nothing), \
                 mock.patch.object(summaries, "reset_once", nothing), mock.patch.object(summaries, "_retry_once", nothing), \
                 mock.patch.object(summaries, "_reask_once", nothing), mock.patch.object(summaries, "log_coverage", nothing), \
                 mock.patch.object(summaries.article_cves, "after_fetch", nothing):
                await summaries.summarize_pending(s)
        self.assertEqual(set(asked), {ids["new"], ids["grew"], ids["fails"]})  # not the one summarized an hour ago
        async with self.Session() as s:
            self.assertTrue((await s.get(Item, ids["new"])).summary.startswith("Researchers found"))
            grew = await s.get(Item, ids["grew"])
            self.assertTrue(grew.summary.startswith("The grew row's product"))
            self.assertEqual(grew.summary_sources, 2)
            fails = await s.get(Item, ids["fails"])
            self.assertEqual(fails.summary, "Kept summary of the fails row.")
            self.assertEqual(fails.summary_sources, 2)  # not asked again until another source joins
            self.assertEqual((await s.get(Item, ids["recent"])).summary, "Recent summary.")

    async def test_merge_keeps_the_survivors_displayed_cve(self):
        now = datetime.now(UTC)
        async with self.Session() as s:
            src = Source(name="The Hacker News", feed_url="https://test.invalid/thn", stream=Stream.main)
            s.add(src)
            await s.flush()
            row = await self._row(s, src, "MikroTrick chain takes over MikroTik routers", now - timedelta(hours=10), ["CVE-2026-67279"])
            other = await self._row(s, src, "MikroTik and SharePoint", now - timedelta(hours=5), ["CVE-2026-67279", "CVE-2026-65660"])
            (await s.get(Cve, "CVE-2026-67279")).base_score = 6.5
            (await s.get(Cve, "CVE-2026-65660")).base_score = 8.8
            await s.commit()
            survivor = article_cves.Row(row.id, now - timedelta(hours=10), now - timedelta(hours=10), False, {"CVE-2026-67279"})
            merged = article_cves.Row(other.id, now - timedelta(hours=5), now - timedelta(hours=5), False, {"CVE-2026-67279", "CVE-2026-65660"})
            await article_cves.merge(s, survivor, merged, "test")
            await s.commit()
            await enrich.roll_up(s)  # pinned: the higher-scored SharePoint CVE does not take over
        async with self.Session() as s:
            item = await s.get(Item, row.id)
            self.assertEqual(item.cve_id, "CVE-2026-67279")
            self.assertEqual(float(item.cvss), 6.5)

    async def test_vendor_fix_data_wins_over_an_unpatched_headline(self):
        # Row 747 (2026-09-30): "Two Unpatched Citrix NetScaler RCE Zero-Days", while NVD's CPE
        # ranges already carried Citrix's fixed builds. The other CVE has no fix data: no fix.
        from app.models import PatchStatus

        now = datetime.now(UTC)
        async with self.Session() as s:
            src = Source(name="The Hacker News", feed_url="https://test.invalid/thn", stream=Stream.main)
            s.add(src)
            await s.flush()
            row = await self._row(s, src, "Warning: Two Unpatched Citrix NetScaler RCE Zero-Days Under Active Exploitation",
                                  now - timedelta(hours=10), ["CVE-2026-88771", "CVE-2026-88772"])
            fixed = await s.get(Cve, "CVE-2026-88771")
            fixed.patch_status, fixed.fixed_versions = PatchStatus.patched, [{"product": "NetScaler ADC", "versions": ["14.1-73.37"]}]
            (await s.get(Cve, "CVE-2026-88772")).patch_status = PatchStatus.unverified
            other = await self._row(s, src, "Unpatched flaw in Acme Router exploited", now - timedelta(hours=5), ["CVE-2026-99999"])
            (await s.get(Cve, "CVE-2026-99999")).patch_status = PatchStatus.unverified
            await s.commit()
            await enrich.roll_up(s)
        async with self.Session() as s:
            self.assertEqual((await s.get(Item, row.id)).patch_status, PatchStatus.patched)
            self.assertEqual((await s.get(Cve, "CVE-2026-88771")).patch_status, PatchStatus.patched)
            self.assertEqual((await s.get(Cve, "CVE-2026-88772")).patch_status, PatchStatus.no_fix)
            self.assertEqual((await s.get(Item, other.id)).patch_status, PatchStatus.no_fix)


if __name__ == "__main__":
    unittest.main()
