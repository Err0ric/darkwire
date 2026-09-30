"""CVE IDs from fetched article text (app/article_cves.py) and the merge re-check after them.

    cd api && python -m unittest discover -s tests
"""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.article_cves import PER_ARTICLE, Row, article_cves, eligible, is_roundup, keep, merge_target, pair, subject_cves
from app.dedupe import alert_row_takes
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


class Tweaks(unittest.TestCase):
    NOW = datetime(2026, 9, 30, tzinfo=UTC)

    def test_subject_cves_title_lede_or_repeated(self):
        text = (
            "Apple shipped fixes on Monday for a CoreGraphics flaw.\n"
            "The bug, CVE-2026-86950, was exploited in targeted attacks.\n"
            "Earlier this year Apple patched CVE-2026-20700 and last year CVE-2025-43300.\n"
            "Mandiant tied the attacks to CVE-2026-35273 before. CVE-2026-35273 remains in use."
        )
        self.assertEqual(
            subject_cves("Apple patches CoreGraphics zero-day", "", text),
            {"CVE-2026-86950", "CVE-2026-35273"},
        )
        # 834 (The Record): the extracted text repeats the headline first; the CVE is in the
        # second body paragraph, still the lede.
        record = (
            "ShinyHunters exploiting workarounds for Oracle PeopleSoft bug, Mandiant warns\n"
            "A vulnerability in Oracle products is being used in a new campaign by ShinyHunters.\n"
            "Mandiant published a blog on Friday about CVE-2026-35273, disclosed in June.\n"
            "Mandiant reported in June that ShinyHunters exploited the bug as a zero-day."
        )
        self.assertEqual(
            subject_cves("ShinyHunters exploiting workarounds for Oracle PeopleSoft bug, Mandiant warns", "", record),
            {"CVE-2026-35273"},
        )
        self.assertIn("CVE-2026-10001", subject_cves("Flaw CVE-2026-10001 exploited", "", ""))
        self.assertIn("CVE-2026-20002", subject_cves("Flaw", "The feed lede names CVE-2026-20002.", ""))

    def test_subject_kept_at_any_age_context_only_with_a_recent_nvd_date(self):
        subject = {"CVE-2026-35273"}
        published = {
            "CVE-2026-35273": datetime(2026, 4, 1, tzinfo=UTC),  # old, but the subject
            "CVE-2026-20700": None,  # context, NVD has no date: dropped (no year fallback)
            "CVE-2025-43300": datetime(2025, 8, 21, tzinfo=UTC),  # context, old: dropped
            "CVE-2026-90000": datetime(2026, 9, 20, tzinfo=UTC),  # context, recent: kept
        }
        kept, dropped = keep(list(published), subject, published, self.NOW)
        self.assertEqual(kept, ["CVE-2026-35273", "CVE-2026-90000"])
        self.assertEqual(dropped, ["CVE-2026-20700", "CVE-2025-43300"])

    def test_recaps_and_roundups(self):
        for title in (
            "⚡ Weekly Recap: $387M Crypto Hack, Citrix Exploits, AI Agents Go Off-Script, and More",
            "Metasploit Wrap Up: Belgian Waffles, Chocolates, and Modules-Frites?",
            "Vulnerability Roundup: September 2026",
            "Patch round-up for the week",
        ):
            self.assertTrue(is_roundup(title), title)
        self.assertFalse(is_roundup("CISA orders feds to patch exploited Citrix flaws by Wednesday"))
        recap = SimpleNamespace(stream=Stream.main, headline="⚡ Weekly Recap: Citrix Exploits",
                                primary_url="https://thehackernews.com/2026/09/weekly-recap.html")
        self.assertFalse(eligible(recap))

    def test_a_recap_never_merges(self):
        r747 = Row(747, CITRIX_747, CITRIX_747, alert=True, cves={"CVE-2026-88771"})
        r815 = Row(815, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-88771"}, roundup=True)
        self.assertIsNone(pair(r815, [r747, r815]))
        self.assertIsNone(pair(r747, [r747, r815]))

    def test_news_joins_an_alert_row_only_when_it_holds_one_cve(self):
        four = Row(85, CITRIX_747, CITRIX_747, alert=True, led=True,
                   cves={"CVE-2026-93952", "CVE-2026-94127", "CVE-2026-1", "CVE-2026-2"})
        f5 = Row(790, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-94127"})
        self.assertIsNone(pair(f5, [four, f5]))
        one = Row(799, CITRIX_747, CITRIX_747, alert=True, led=True, cves={"CVE-2026-94127"})
        self.assertEqual(pair(f5, [one, f5]), (one, f5))

    def test_news_holding_all_of_a_multi_cve_alerts_cves_joins_it(self):
        # 795 (WSO2 and Adobe Commerce) names both CVEs CISA's alert row 794 holds.
        r794 = Row(794, CITRIX_747, CITRIX_747, alert=True, led=True, cves={"CVE-2026-5430", "CVE-2026-71362"})
        r795 = Row(795, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-5430", "CVE-2026-71362"})
        self.assertEqual(pair(r795, [r794, r795]), (r794, r795))
        one = Row(796, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-5430"})
        self.assertIsNone(pair(one, [r794, one]))
        self.assertTrue(alert_row_takes({"A", "B"}, {"A", "B", "C"}))
        self.assertFalse(alert_row_takes({"A", "B"}, {"A"}))
        self.assertTrue(alert_row_takes({"A"}, {"A"}))

    def test_a_multi_story_row_never_merges(self):
        # 797 names SharePoint and MikroTik CVEs: they attach, it merges nowhere.
        r793 = Row(793, CITRIX_747, CITRIX_747, alert=False, cves={"CVE-2026-67279", "CVE-2026-86060"})
        r797 = Row(797, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-65660", "CVE-2026-67279"}, multi_story=True)
        self.assertIsNone(pair(r797, [r793, r797]))
        self.assertIsNone(pair(r793, [r793, r797]))

    def test_a_news_row_an_alert_joined_still_takes_news(self):
        # Row 747 is THN's story; CISA's alert joined it. It is not alert-led.
        r747 = Row(747, CITRIX_747, CITRIX_747, alert=True, led=False, cves={"CVE-2026-88771", "CVE-2026-88772"})
        r801 = Row(801, CITRIX_801, CITRIX_801, alert=False, cves={"CVE-2026-88771", "CVE-2026-88772"})
        self.assertEqual(pair(r801, [r747, r801]), (r747, r801))


if __name__ == "__main__":
    unittest.main()
