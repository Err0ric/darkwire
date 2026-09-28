"""Clustering rules (app/dedupe.py): a CISA KEV alert joins the one row already holding all its
CVEs, else starts its own row, which a news article joins only through a CVE the alert lists;
title merges need 72h, and without a vendor they compare titles with boilerplate removed.

    cd api && python -m unittest discover -s tests
"""

import unittest
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app import alerts, dedupe
from app.dedupe import Art, plan
from app.tagging import VendorMatcher

MICROSOFT, CITRIX = 1, 2
MATCHER = VendorMatcher([
    SimpleNamespace(id=MICROSOFT, name="Microsoft", aliases=["Microsoft", "SharePoint"]),
    SimpleNamespace(id=CITRIX, name="Citrix", aliases=["Citrix", "NetScaler"]),
])


def at(day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def alert(day: int, count: str, cves: list[str], slug: str = "") -> Art:
    noun = "Vulnerability" if count == "One" else "Vulnerabilities"
    url = f"https://www.cisa.gov/news-events/alerts/2026/09/{day:02d}/cisa-adds-{count.lower()}-known-exploited-{noun.lower()}-catalog{slug}"
    return Art(url, f"CISA Adds {count} Known Exploited {noun} to Catalog", url, at(day), None, cves)


def news(key: str, title: str, when: datetime, cves=(), vendor=None) -> Art:
    return Art(key, title, f"https://news.example/{key}", when, vendor, list(cves))


def keys(groups) -> list[list[str]]:
    return sorted(sorted(str(a.key) for a in g.arts) for g in groups)


class KevAlerts(unittest.TestCase):
    def test_alerts_from_different_days_stay_separate(self):
        a, b = alert(24, "Two", ["CVE-2026-1"]), alert(25, "Two", ["CVE-2026-2"])
        self.assertEqual(len(plan([a, b], MATCHER)), 2)

    def test_alerts_on_the_same_day_stay_separate(self):
        a = alert(25, "Two", ["CVE-2026-65660", "CVE-2026-67279"])
        b = alert(25, "One", ["CVE-2026-87902"])
        self.assertEqual(len(plan([a, b], MATCHER)), 2)

    def test_alerts_sharing_a_cve_stay_separate(self):
        a, b = alert(24, "One", ["CVE-2026-1"]), alert(25, "One", ["CVE-2026-1"])
        self.assertEqual(len(plan([a, b], MATCHER)), 2)

    def test_an_article_sharing_a_cve_joins_the_right_alert(self):
        a = alert(24, "Two", ["CVE-2026-1", "CVE-2026-2"])
        b = alert(25, "Two", ["CVE-2026-65660", "CVE-2026-67279"])
        sharepoint = news("thn", "Microsoft SharePoint Flaw CVE-2026-65660 Now Exploited", at(25, 17), ["CVE-2026-65660"], MICROSOFT)
        groups = plan([a, b, sharepoint], MATCHER)
        joined = next(g for g in groups if any(x.key == "thn" for x in g.arts))
        self.assertEqual([x.key for x in joined.arts if x.alert], [b.key])
        self.assertEqual(len(groups), 2)

    def test_an_unrelated_article_does_not_join(self):
        a = alert(25, "Two", ["CVE-2026-65660", "CVE-2026-67279"])
        other = news("f5", "F5 Patches Critical BIG-IP APM Zero-Day", at(25, 13), ["CVE-2026-94127"])
        no_cve = news("vague", "CISA warns of more exploited flaws", at(25, 14))
        self.assertEqual(len(plan([a, other, no_cve], MATCHER)), 3)

    def test_an_alert_row_keeps_only_the_alerts_cves(self):
        # Joining news brings its other CVEs; a later article sharing only those must not chain on.
        a = alert(25, "One", ["CVE-2026-87902"])
        wp = news("wp", "WordPress CVE-2026-87902 exploited alongside CVE-2026-5000", at(25, 15), ["CVE-2026-87902", "CVE-2026-5000"])
        later = news("later", "Another bug CVE-2026-5000", at(25, 18), ["CVE-2026-5000"])
        groups = plan([a, wp, later], MATCHER)
        self.assertEqual(keys(groups), sorted([sorted([a.key, "wp"]), ["later"]]))

    def test_citrix_alert_joins_the_row_holding_all_its_cves(self):
        thn = news("thn", "Warning: Two Unpatched Citrix NetScaler RCE Zero-Days Under Active Exploitation", at(27, 7, 47), ["CVE-2026-88771", "CVE-2026-88772"], CITRIX)
        amplify = Art("cisa-amplify", "Critical Zero-Day Vulnerabilities Exploited in Citrix NetScaler ADC, Gateway",
                      "https://www.cisa.gov/news-events/alerts/2026/09/27/critical-zero-day-vulnerabilities-exploited-citrix-netscaler-adc-gateway",
                      at(27), CITRIX, ["CVE-2026-88771"])
        bc = news("bc", "Citrix admins warned to shut down NetScalers over 2 exploited zero-days", at(27, 16, 2), ["CVE-2026-88771", "CVE-2026-88772"], CITRIX)
        kev = alert(27, "Two", ["CVE-2026-88771", "CVE-2026-88772"])
        groups = plan([thn, amplify, bc, kev], MATCHER)
        self.assertEqual(len(groups), 1)
        row = groups[0]
        self.assertEqual(row.arts[0].key, "thn")  # the row keeps its own headline
        self.assertEqual(row.time, at(27, 7, 47))  # and its own time
        self.assertTrue(row.has_alert and not row.alert_led)

    def test_wordpress_alert_joins_the_earlier_article(self):
        thn = news("thn", "Attackers Exploit WordPress CVE-2026-87902 Within Hours of Disclosure", at(24, 5, 36), ["CVE-2026-87902"])
        kev = alert(25, "One", ["CVE-2026-87902"])
        groups = plan([thn, kev], MATCHER)
        self.assertEqual(keys(groups), [sorted(["thn", kev.key])])
        self.assertEqual(groups[0].time, at(24, 5, 36))

    def test_sharepoint_mikrotik_alert_spans_two_rows_and_stays_separate(self):
        sharepoint = news("sp", "SharePoint Flaw Initially Listed as Spoofing by Microsoft Enables Auth Bypass", at(24, 11), ["CVE-2026-65660"], MICROSOFT)
        mikrotik = news("mt", "MikroTrick Chain Let Attackers Take Over MikroTik Routers Without a Password", at(24, 16), ["CVE-2026-67279"])
        kev = alert(25, "Two", ["CVE-2026-65660", "CVE-2026-67279"])
        groups = plan([sharepoint, mikrotik, kev], MATCHER)
        self.assertEqual(keys(groups), sorted([["sp"], ["mt"], [kev.key]]))

    def test_an_alert_does_not_join_when_two_rows_hold_all_its_cves(self):
        one = news("a", "WordPress core flaw CVE-2026-87902 exploited", at(24, 5), ["CVE-2026-87902"])
        two = news("b", "Unrelated plugin roundup mentions CVE-2026-87902", at(20, 5), ["CVE-2026-87902"])
        kev = alert(25, "One", ["CVE-2026-87902"])
        self.assertEqual(len(plan([one, two, kev], MATCHER)), 3)

    def test_an_alert_never_joins_a_row_that_already_has_one(self):
        thn = news("thn", "Attackers Exploit WordPress CVE-2026-87902", at(24, 5), ["CVE-2026-87902"])
        first, again = alert(25, "One", ["CVE-2026-87902"]), alert(26, "One", ["CVE-2026-87902"], "-2")
        groups = plan([thn, first, again], MATCHER)
        self.assertEqual(keys(groups), sorted([sorted(["thn", first.key]), [again.key]]))

    def test_a_row_an_alert_joined_still_takes_news(self):
        thn = news("thn", "Attackers Exploit WordPress CVE-2026-87902", at(24, 5), ["CVE-2026-87902"])
        kev = alert(25, "One", ["CVE-2026-87902"])
        later = news("sw", "WordPress CVE-2026-87902 attacks spread", at(25, 20), ["CVE-2026-87902"])
        self.assertEqual(len(plan([thn, kev, later], MATCHER)), 1)

    def test_a_row_time_ignores_a_joined_alert(self):
        rows = [SimpleNamespace(title="x", url="https://news.example/x", published_at=at(25, 13)),
                SimpleNamespace(title="CISA Adds One Known Exploited Vulnerability to Catalog",
                                url="https://www.cisa.gov/news-events/alerts/2026/09/25/a", published_at=at(25, 12))]
        self.assertEqual([s.published_at for s in dedupe.time_sources(rows)], [at(25, 13)])
        self.assertEqual(len(dedupe.time_sources(rows[1:])), 1)  # an alert alone keeps its own time

    def test_a_row_an_alert_started_keeps_the_alerts_time(self):
        kev = alert(22, "Four", ["CVE-2026-94127"])
        rapid7 = news("r7", "CVE-2026-94127: Critical Unauthenticated RCE in F5 BIG-IP APM", at(23, 8, 43), ["CVE-2026-94127"])
        groups = plan([kev, rapid7], MATCHER)
        self.assertEqual((len(groups), groups[0].time), (1, at(22)))

    def test_a_headline_count_fills_the_rows_cves_for_an_alert(self):
        # Only the lead of one article names the second CVE; the headline counts two, as ingest
        # links them the row holds both, so the alert listing both joins it.
        thn = news("thn", "Warning: Two Unpatched Citrix NetScaler RCE Zero-Days Under Active Exploitation", at(27, 7, 47), ["CVE-2026-88771"], CITRIX)
        thn.lead = "Citrix disclosed CVE-2026-88771 and CVE-2026-88772, both exploited."
        bc = news("bc", "Citrix admins warned to shut down NetScalers", at(27, 9), ["CVE-2026-88771"], CITRIX)
        kev = alert(27, "Two", ["CVE-2026-88771", "CVE-2026-88772"])
        self.assertEqual(len(plan([thn, bc, kev], MATCHER)), 1)

    def test_another_outlets_copy_of_the_title_is_news(self):
        self.assertTrue(dedupe.is_kev_alert("CISA Adds One Known Exploited Vulnerability to Catalog", "https://www.cisa.gov/news-events/alerts/x"))
        self.assertFalse(dedupe.is_kev_alert("CISA Adds One Known Exploited Vulnerability to Catalog", "https://thehackernews.com/x"))
        self.assertFalse(dedupe.is_kev_alert("Critical Zero-Day Vulnerabilities Exploited in Citrix NetScaler", "https://www.cisa.gov/news-events/alerts/x"))


class TitleMerges(unittest.TestCase):
    def test_boilerplate_titles_alone_never_merge(self):
        a = news("a", "CISA Adds Two Known Exploited Vulnerabilities to KEV Catalog", at(24))
        b = news("b", "CISA Adds Two Known Exploited Vulnerabilities to KEV Catalog", at(25))
        self.assertEqual(len(plan([a, b], MATCHER)), 2)

    def test_same_vendor_similar_titles_within_72h_merge(self):
        a = news("a", "Citrix NetScaler zero-day exploited in attacks", at(24), vendor=CITRIX)
        b = news("b", "Citrix NetScaler zero-day exploited in attacks now", at(26, 11), vendor=CITRIX)
        self.assertEqual(len(plan([a, b], MATCHER)), 1)

    def test_not_after_72h(self):
        a = news("a", "Citrix NetScaler zero-day exploited in attacks", at(20), vendor=CITRIX)
        b = news("b", "Citrix NetScaler zero-day exploited in attacks now", at(20) + timedelta(hours=73), vendor=CITRIX)
        self.assertEqual(len(plan([a, b], MATCHER)), 2)

    def test_stories_with_no_cve_or_vendor_merge_again(self):
        pairs = [
            ("Rydox marketplace admin pleads guilty, faces 22 years in prison", at(25, 11, 35),
             "Kosovar Owner of Rydox Marketplace Pleads Guilty in US Court", at(25, 12, 16)),
            ("North Korea Suspected in $351 Million Bitget Crypto Heist", at(25, 14, 16),
             "Crypto CEO accuses North Korea of stealing $387 million from Bitget platform", at(25, 15, 15)),
            ("OpenAI Agent Bypassed Australian Medicare Portal Controls to Access Non-Public Files", at(24, 7, 7),
             "Doubts grow over claims OpenAI agent hacked Australian Medicare portal", at(25, 12)),
            ("Kiteworks urges customers to shut down servers", at(24),
             "Kiteworks customers told to shut down servers now", at(24, 18)),
        ]
        for t1, p1, t2, p2 in pairs:
            with self.subTest(t1):
                self.assertEqual(len(plan([news("a", t1, p1), news("b", t2, p2)], MATCHER)), 1)

    def test_kev_alert_titles_never_match(self):
        t1 = "CISA Adds Two Known Exploited Vulnerabilities to Catalog"
        t2 = "CISA Adds Two Known Exploited Vulnerabilities to Catalog"
        self.assertFalse(dedupe.titles_match(t1, t2, None, None, MATCHER))
        self.assertEqual(len(plan([alert(24, "Two", []), alert(25, "Two", [])], MATCHER)), 2)


class AlertCves(unittest.TestCase):
    def test_date_and_count(self):
        url = "https://www.cisa.gov/news-events/alerts/2026/09/21/cisa-adds-one-known-exploited-vulnerability-catalog"
        self.assertEqual(alerts.alert_date(url, None), date(2026, 9, 21))
        self.assertEqual(alerts.alert_count("CISA Adds One Known Exploited Vulnerability to Catalog"), 1)
        self.assertEqual(alerts.alert_count("CISA Adds Four Known Exploited Vulnerabilities to Catalog"), 4)


class TheCase(unittest.TestCase):
    """Row 93 on production: three CISA alerts (09-21, 09-24, 09-25) and five stories chained
    into one row. Under the rules each alert is its own row and each story goes with the alert
    that lists its CVE, or stands alone."""

    def test_row_93_splits(self):
        arts = [
            alert(21, "One", ["CVE-2026-7273"]),
            news("thn-sharepoint-spoof", "SharePoint Flaw Initially Listed as Spoofing by Microsoft Enables Auth Bypass", at(22, 11, 17), ["CVE-2026-65660"], MICROSOFT),
            news("thn-mikrotik", "MikroTrick Chain Let Attackers Take Over MikroTik Routers Without a Password", at(23, 16, 6), ["CVE-2026-67279"]),
            alert(24, "Two", ["CVE-2026-5430", "CVE-2026-5431"]),
            news("thn-wso2", "WSO2 and Adobe Commerce Flaws Exploited in Attacks, Added to CISA KEV", at(25, 4, 46), ["CVE-2026-5430", "CVE-2026-5431"]),
            alert(25, "Two", ["CVE-2026-65660", "CVE-2026-67279"]),
            news("bc", "CISA warns of Sharepoint, WSO2, Adobe Commerce flaws exploited in attacks", at(25, 17, 24), ["CVE-2026-65660"], MICROSOFT),
            news("thn-rce", "SharePoint RCE and MikroTik RouterOS Flaws Actively Exploited in the Wild", at(26, 8, 49), ["CVE-2026-65660", "CVE-2026-67279"], MICROSOFT),
        ]
        groups = plan(arts, MATCHER)
        self.assertEqual(sum(g.alert_led for g in groups), 3)
        by_alert = {next(a.key for a in g.arts if a.alert)[-60:]: sorted(str(a.key) for a in g.arts if not a.alert) for g in groups if g.alert_led}
        self.assertIn(["thn-wso2"], by_alert.values())  # joins the 09-24 alert listing its CVEs
        self.assertIn(["bc", "thn-rce"], by_alert.values())  # join the 09-25 alert
        self.assertTrue(all(len(g.arts) == 1 for g in groups if not g.alert_led))  # the rest stand alone


if __name__ == "__main__":
    unittest.main()
