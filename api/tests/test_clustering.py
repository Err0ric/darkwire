"""Clustering rules (app/dedupe.py): CISA KEV alerts are their own rows, a news article joins
one only through a CVE the alert lists, and title merges need 72h plus a shared CVE or vendor.

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

    def test_shared_words_need_a_shared_cve_or_vendor(self):
        a = news("a", "Kiteworks urges customers to shut down servers", at(24))
        b = news("b", "Kiteworks customers told to shut down servers now", at(24, 18))
        self.assertEqual(len(plan([a, b], MATCHER)), 2)
        a.cves = b.cves = ["CVE-2026-4242"]
        self.assertEqual(len(plan([a, b], MATCHER)), 1)


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
        self.assertEqual(sum(g.alert for g in groups), 3)
        by_alert = {next(a.key for a in g.arts if a.alert)[-60:]: sorted(str(a.key) for a in g.arts if not a.alert) for g in groups if g.alert}
        self.assertIn(["thn-wso2"], by_alert.values())  # joins the 09-24 alert listing its CVEs
        self.assertIn(["bc", "thn-rce"], by_alert.values())  # join the 09-25 alert
        self.assertTrue(all(len(g.arts) == 1 for g in groups if not g.alert))  # the rest stand alone


if __name__ == "__main__":
    unittest.main()
