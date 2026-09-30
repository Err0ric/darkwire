"""CVE IDs from fetched article text (app/article_cves.py) and the merge re-check after them.

    cd api && python -m unittest discover -s tests
"""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.article_cves import PER_ARTICLE, Row, article_cves, eligible, gained, merge_target, pair
from app.fetcher import main_body
from app.models import Stream

CITRIX_747 = datetime(2026, 9, 27, 7, 47, tzinfo=UTC)  # row 747: THN, the Citrix zero-days
CITRIX_801 = datetime(2026, 9, 28, 6, 24, tzinfo=UTC)  # row 801: BleepingComputer, no CVE in its feed text


class Extraction(unittest.TestCase):
    def test_ids_in_the_fetched_text(self):
        body = "CISA ordered agencies to patch CVE-2026-88771 and CVE-2026-88772 in NetScaler by Wednesday."
        self.assertEqual(
            article_cves("CISA orders feds to patch exploited Citrix flaws by Wednesday", "", body),
            ["CVE-2026-88771", "CVE-2026-88772"],
        )

    def test_malformed_ids_are_ignored(self):
        self.assertEqual(article_cves("Flaw", "", "Not CVE-26-1234 nor CVE-2026-12 nor CVE2026-12345."), [])

    def test_at_most_ten_per_article(self):
        ids = [f"CVE-2026-{1000 + i}" for i in range(15)]
        title = "Fifteen flaws: " + " ".join(ids)  # in the title, so all are tied
        self.assertEqual(len(article_cves(title, "", "")), PER_ARTICLE)

    def test_a_bulletin_listed_in_passing_does_not_attach(self):
        body = (
            "Attackers exploited CVE-2026-50001 in the wild. The update also fixes CVE-2026-50002, "
            "CVE-2026-50003, CVE-2026-50004 and CVE-2026-50005."
        )
        self.assertEqual(article_cves("Zero-Day Exploited in Attacks", "", body), ["CVE-2026-50001"])

    def test_related_articles_do_not_count(self):
        text = "Citrix fixed CVE-2026-88771.\nRelated: Fortinet patches CVE-2026-11111\nRelated Articles\nOther CVE-2026-22222"
        self.assertEqual(article_cves("Citrix flaw", "", main_body(text)), ["CVE-2026-88771"])

    def test_only_fetched_text_is_read(self):
        # gained() reads the fetched article per source id and nothing else (never a summary).
        src = SimpleNamespace(id=7, title="Citrix flaws", excerpt="")
        item = SimpleNamespace(sources=[src], summary="The model mentioned CVE-2026-99999.")
        self.assertEqual(gained(item, {}, set()), [])
        self.assertEqual(gained(item, {7: "Fixes CVE-2026-88771."}, set()), ["CVE-2026-88771"])
        self.assertEqual(gained(item, {7: "Fixes CVE-2026-88771."}, {"CVE-2026-88771"}), [])

    def test_alert_rows_and_ics_advisories_are_left_alone(self):
        alert = SimpleNamespace(
            stream=Stream.main, headline="CISA Adds Two Known Exploited Vulnerabilities to Catalog",
            primary_url="https://www.cisa.gov/news-events/alerts/2026/09/27/cisa-adds-two-known-exploited-vulnerabilities-catalog",
        )
        advisory = SimpleNamespace(stream=Stream.main, headline="Baicells Nova 430H",
                                   primary_url="https://www.cisa.gov/news-events/ics-advisories/icsa-26-272-04")
        news = SimpleNamespace(stream=Stream.main, headline="CISA orders feds to patch exploited Citrix flaws",
                               primary_url="https://www.bleepingcomputer.com/news/security/x/")
        self.assertFalse(eligible(alert))
        self.assertFalse(eligible(advisory))
        self.assertTrue(eligible(news))


class Merges(unittest.TestCase):
    def test_801_joins_747_once_it_shares_a_cve(self):
        r747 = Row(747, CITRIX_747, CITRIX_747, alert=True, cves={"CVE-2026-88771", "CVE-2026-88772"})
        r801 = Row(801, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-88771"})
        self.assertIs(merge_target(r801, [r747, r801]), r747)
        self.assertEqual(pair(r801, [r747, r801]), (r747, r801))

    def test_an_earlier_row_that_gains_a_cve_takes_in_the_later_one(self):
        early = Row(1, CITRIX_747, CITRIX_747, alert=False, cves={"CVE-2026-88771"})
        late = Row(2, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-88771"})
        self.assertEqual(pair(early, [early, late]), (early, late))

    def test_outside_72_hours_no_merge(self):
        old = Row(1, CITRIX_747, CITRIX_747, alert=False, cves={"CVE-2026-88771"})
        later = Row(2, CITRIX_747 + timedelta(hours=73), CITRIX_747 + timedelta(hours=73), alert=False, cves={"CVE-2026-88771"})
        self.assertIsNone(pair(later, [old, later]))

    def test_no_shared_cve_no_merge(self):
        a = Row(1, CITRIX_747, CITRIX_747, alert=False, cves={"CVE-2026-1"})
        b = Row(2, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-2"})
        self.assertIsNone(pair(b, [a, b]))

    def test_an_alert_never_joins_another_row(self):
        news = Row(1, CITRIX_747, CITRIX_747, alert=False, cves={"CVE-2026-88771"})
        alert = Row(2, CITRIX_801, CITRIX_801, alert=True, cves={"CVE-2026-88771"})
        self.assertIsNone(merge_target(alert, [news, alert]))
        self.assertIsNone(pair(news, [news, alert]))


if __name__ == "__main__":
    unittest.main()
