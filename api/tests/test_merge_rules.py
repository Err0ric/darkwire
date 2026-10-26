"""News-into-news merges on a shared CVE (app/article_cves.py takes): the CVE must be what both
rows are about, and a row's only CVE is what it is about when it is the row's vendor's.

    cd api && python -m unittest discover -s tests
"""

import unittest
from datetime import UTC, datetime

from app.article_cves import Row, takes
from app.tagging import subject_cves

T = datetime(2026, 9, 30, 6, 55, tzinfo=UTC)
CVE = "CVE-2026-84782"

# Rows 907 and 910 (2026-09-30): each article names the CVE once, below the lede.
SECURITYWEEK = ("High-Severity Vulnerabilities Patched in OpenSSL, WolfSSL",
                "OpenSSL and WolfSSL have released patches for multiple high-severity vulnerabilities.")
THN = ("OpenSSL Fixes High-Severity DTLS Flaw That Can Leak Heap Memory Unencrypted",
       "OpenSSL has released fixes for a high-severity flaw in its DTLS implementation.")


def row(i, title, lead, cves, solo=True):
    return Row(i, T, T, False, cves=set(cves), subject=subject_cves(title, lead, ""), solo=solo)


class SingleCveRows(unittest.TestCase):
    def test_the_openssl_rows_merge(self):
        old, new = row(907, *SECURITYWEEK, [CVE]), row(910, *THN, [CVE])
        self.assertEqual(old.subject | new.subject, set())  # not a subject by the lede rule
        self.assertTrue(takes(old, new))

    def test_a_single_cve_of_another_vendor_is_still_context(self):
        # 819 (an arrest story) held one Oracle CVE it only mentioned; 834 was about it.
        self.assertFalse(takes(row(819, "Soldier sentenced for extortions", "", [CVE], solo=False), row(834, *THN, [CVE])))

    def test_a_context_cve_of_a_multi_cve_row_still_does_not_merge(self):
        old = row(1, "Patch Tuesday fixes 60 flaws", "Microsoft fixed 60 flaws this month.", [CVE, "CVE-2026-11111"])
        self.assertFalse(takes(old, row(2, *THN, [CVE])))

    def test_different_single_cves_do_not_merge(self):
        self.assertFalse(takes(row(1, *SECURITYWEEK, [CVE]), row(2, *THN, ["CVE-2026-22222"])))


class Exclusions(unittest.TestCase):
    def test_an_excluded_pair_never_merges(self):
        from app import dedupe
        from app.article_cves import merge_target, pair

        # 819 and 1 (2026-09-30): the rules would merge them; the exclusion says no, either way.
        r1 = Row(1, T, T, False, cves={CVE}, subject={CVE})
        r819 = Row(819, T.replace(hour=9), T.replace(hour=9), False, cves={CVE}, subject={CVE})
        self.assertTrue(takes(r1, r819))
        self.assertTrue(dedupe.excluded(819, 1) and dedupe.excluded(1, 819))
        self.assertIsNone(merge_target(r819, [r1]))
        self.assertIsNone(pair(r819, [r1, r819]))
        self.assertIsNone(pair(r1, [r1, r819]))
        # Any other pair with the same data still merges.
        r2 = Row(2, T.replace(hour=9), T.replace(hour=9), False, cves={CVE}, subject={CVE})
        self.assertIs(merge_target(r2, [r1]), r1)


if __name__ == "__main__":
    unittest.main()


class PhpExclusion(unittest.TestCase):
    def test_the_new_php_cve_row_stays_out_of_php2shell(self):
        from app import dedupe
        from app.article_cves import merge_target

        # 2026-10-25: 1760/1766 hold THN's CVE-2026-115560 article as a subject; 1927 is about it.
        new = "CVE-2026-115560"
        old = Row(1760, T, T, False, cves={"CVE-2026-109618", new}, subject={"CVE-2026-109618", new})
        r1927 = Row(1927, T.replace(hour=9), T.replace(hour=9), False, cves={new}, subject={new})
        self.assertTrue(takes(old, r1927))
        for survivor in (1760, 1766):
            self.assertTrue(dedupe.excluded(1927, survivor) and dedupe.excluded(survivor, 1927))
            old.id = survivor
            self.assertIsNone(merge_target(r1927, [old]))


class IntroducedCves(unittest.TestCase):
    """2026-10-22/24: "tracked as CVE-..." below the lede made the CVE no article's subject, so the
    VeloCloud rows (prod 1871, 1891) and the Popcorn Time rows (1948, 1952) never merged."""

    VELO = "CVE-2026-114625"
    BC = ("Arista patches new VeloCloud Orchestrator zero-day exploited in attacks", "",
          "Arista Networks released security updates to patch an actively exploited zero-day.\n"
          "VCO is a web-based management portal.\n"
          "Tracked as CVE-2026-114625, this critical-severity flaw can allow attackers to escalate privileges.\n"
          "This year, Arista has patched three other actively exploited zero-day flaws (CVE-2026-7473 in May, "
          "CVE-2026-16812 in July, and CVE-2026-93952 in September).")
    THN = ("Arista Warns of Critical VeloCloud SQL Injection Zero-Day Exploited in Attacks", "",
           "Attackers are exploiting a zero-day SQL injection flaw in Arista's VeloCloud Orchestrator.\n"
           "The flaw lets anyone who can log in gain operator privileges.\n"
           "For on-premises orchestrators, the fix is in VCO 5.2.3.18.\n"
           "The flaw is tracked as CVE-2026-114625 and rated 9.9 on the CVSS scale.\n"
           "Neither the July flaw (CVE-2026-16812) nor the September flaw (CVE-2026-93952) needed one.")

    def test_tracked_as_makes_the_subject_and_context_stays_context(self):
        self.assertEqual(subject_cves(*self.BC), {self.VELO})
        self.assertEqual(subject_cves(*self.THN), {self.VELO})

    def test_the_velocloud_rows_merge(self):
        cves = {self.VELO, "CVE-2026-93952"}
        old = Row(1871, T, T, False, cves=cves, subject=subject_cves(*self.BC))
        new = Row(1891, T, T, False, cves=cves | {"CVE-2026-16812"}, subject=subject_cves(*self.THN))
        self.assertTrue(takes(old, new))

    def test_the_forms(self):
        a, b = "CVE-2026-109618", "CVE-2026-109619"
        self.assertEqual(subject_cves("t", "", "x\ny\nTracked as CVE-2026-109618 and CVE-2026-109619, both are rated 9.2."), {a, b})
        self.assertEqual(subject_cves("t", "", "x\ny\nThe bug, identified as CVE-2026-109618, is critical."), {a})
        self.assertEqual(subject_cves("t", "", "x\ny\nIt was assigned CVE-2026-109618."), {a})
        self.assertEqual(subject_cves("t", "", "x\ny\nIt has been assigned the identifier CVE-2026-109618."), {a})
        self.assertEqual(subject_cves("t", "Eye had disclosed the flaw, now tracked as CVE-2026-30612, in June.", ""), {"CVE-2026-30612"})
        # Named once, below the lede, without an introducer: still context.
        self.assertEqual(subject_cves("t", "", "x\ny\nIt recalls CVE-2024-3400, exploited last year."), set())
        self.assertEqual(subject_cves("t", "", "x\ny\nResearchers tracked CVE-2024-3400 activity."), set())


class AlertHome(unittest.TestCase):
    """A KEV alert's own row joins the one other row holding all its CVEs (prod 1944, 2026-10-23)."""

    def test_exactly_one_row(self):
        from app.article_cves import alert_home

        cve = "CVE-2026-114625"
        alert = Row(1944, T, T, True, cves={cve}, led=True)
        news = Row(1871, T, T, False, cves={cve, "CVE-2026-93952"})
        other = Row(1908, T, T, False, cves={cve})
        self.assertIs(alert_home(alert, [alert, news]), news)
        self.assertIsNone(alert_home(alert, [alert, news, other]))  # two rows hold it
        self.assertIsNone(alert_home(alert, [alert, Row(5, T, T, False, cves={"CVE-2026-1"})]))  # none does
        self.assertIsNone(alert_home(alert, [alert, Row(6, T, T, True, cves={cve})]))  # it has an alert
        self.assertIsNone(alert_home(alert, [alert, Row(7, T, T, False, cves={cve}, roundup=True)]))  # a recap
        two = Row(1945, T, T, True, cves={cve, "CVE-2026-2"}, led=True)
        self.assertIsNone(alert_home(two, [two, news]))  # the row must hold every CVE it lists


class BreachShadow(unittest.TestCase):
    """2026-10-22/23 (prod 1893/1905, 1906/1915): breach rows naming one victim, never merged."""

    def test_the_victim_is_found(self):
        from app.dedupe import breach_victims

        self.assertEqual(breach_victims("Capcom confirms data breach affecting 11.7 million accounts",
                                        "11 Million Impacted by Capcom Data Breach"), ["capcom"])
        self.assertEqual(breach_victims("Quest Diagnostics Reports Cyber Breach Affecting 'Certain Patient Records'",
                                        "Quest Diagnostics warns of potential data theft after attack on lab service system"),
                         ["diagnostic", "quest"])
        # Both titles in Title Case: capitals say nothing, so nothing is found (P3 lists this miss).
        self.assertEqual(breach_victims("State Bank of India Confirms Data Leak After 3,897 Customer Records Found on Dark Web",
                                        "State Bank of India Suffers a Customer PII Data Leak"), [])
        self.assertEqual(breach_victims("Capcom confirms data breach", "Railway warns devs to rotate secrets after breach"), [])



def live_merge_rules(on: bool):
    """LIVE_MERGE_RULES for the duration of a with block (settings are cached)."""
    import contextlib
    import os
    from unittest import mock

    from app.config import get_settings

    @contextlib.contextmanager
    def ctx():
        with mock.patch.dict(os.environ, {"LIVE_MERGE_RULES": "true" if on else "false"}):
            get_settings.cache_clear()
            try:
                yield
            finally:
                get_settings.cache_clear()
        get_settings.cache_clear()

    return ctx()


class LiveFlag(unittest.TestCase):
    def test_tracked_as_follows_the_flag(self):
        text = "x\ny\nThe flaw is tracked as CVE-2026-114625."
        with live_merge_rules(False):
            self.assertEqual(subject_cves("t", "", text), set())
            self.assertEqual(subject_cves("t", "", text, introduced=True), {"CVE-2026-114625"})  # the re-merge script
        with live_merge_rules(True):
            self.assertEqual(subject_cves("t", "", text), {"CVE-2026-114625"})
        self.assertEqual(subject_cves("t", "", text), {"CVE-2026-114625"})  # default on


class AlertsToRehome(unittest.TestCase):
    """Only alerts sharing a CVE with a row the pass changed move; held rows never do."""

    def setUp(self):
        self.cve, self.other = "CVE-2026-114625", "CVE-2026-110447"
        self.alert = Row(1944, T, T, True, cves={self.cve}, led=True)
        self.news = Row(1871, T, T, False, cves={self.cve})
        self.old_alert = Row(1500, T, T, True, cves={self.other}, led=True)
        self.old_home = Row(1498, T, T, False, cves={self.other})
        self.rows = {r.id: r for r in (self.alert, self.news, self.old_alert, self.old_home)}

    def test_only_touched_alerts(self):
        from app.article_cves import alerts_to_rehome

        got = alerts_to_rehome(self.rows, touched={1871})
        self.assertEqual([(a.id, h.id) for a, h in got], [(1944, 1871)])  # 1500 is not touched: stays
        self.assertEqual(alerts_to_rehome(self.rows, touched=set()), [])

    def test_held_rows_are_skipped_and_logged(self):
        from app.article_cves import alerts_to_rehome

        with self.assertLogs("app.article_cves", level="INFO") as logs:
            self.assertEqual(alerts_to_rehome(self.rows, touched={1871, 1498}, held=frozenset({1944})),
                             [(self.old_alert, self.old_home)])
        self.assertIn("KEV alert item 1944 would join item 1871, skipped", "\n".join(logs.output))


class P1SignOff(unittest.TestCase):
    def test_the_signed_off_merges_are_the_prod_dry_run(self):
        from app import p1_remerge

        # 2026-10-25 prod dry run: 6 merges, each one EXPECTED listed; 1908 came in by CVE.
        self.assertEqual(len(p1_remerge.SIGNED_OFF), 6)
        self.assertLessEqual(p1_remerge.SIGNED_OFF, p1_remerge.EXPECTED)
        self.assertLessEqual(len(p1_remerge.SIGNED_OFF), p1_remerge.MAX_MERGES)
        merged = [m for _, m, _ in p1_remerge.SIGNED_OFF]
        self.assertEqual(len(merged), len(set(merged)))  # each row merges once
        self.assertEqual({(m, s) for _, m, s in p1_remerge.SIGNED_OFF},
                         {(1766, 1760), (1836, 1760), (1891, 1871), (1908, 1871), (1952, 1948), (1944, 1871)})
