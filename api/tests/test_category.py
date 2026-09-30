"""Category rules (app/tagging.py guess_category): a breach is an incident, an explainer is not.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app.models import Category
from app.tagging import guess_category


class Breach(unittest.TestCase):
    def test_an_explainer_is_research_or_news(self):
        # Row 922 (The Hacker News, 2026-09-30) was tagged BREACH from its first paragraph.
        self.assertEqual(
            guess_category("Know Your Enemy: Browser-Based Attack Techniques in 2026",
                           "Browser-based attacks are now a leading cause of breaches.", False),
            Category.research,
        )
        self.assertEqual(guess_category("Cloud security trends for CISOs", "Breaches are rising.", False), Category.news)
        self.assertEqual(guess_category("How to respond to a data breach", "", False), Category.news)

    def test_an_incident_is_a_breach(self):
        self.assertEqual(guess_category("Pentagon Personnel Agency Data Breach Impacts 3 Million People", "", False), Category.breach)
        self.assertEqual(
            guess_category("Labcorp to overhaul data security practices",
                           "The company suffered a breach that exposed data of 10.2 million customers.", False),
            Category.breach,
        )

    def test_incident_words_in_the_title_count(self):
        # Rows 25 and 896 (2026-09-30): "breach" only in the lead, the incident in the title.
        self.assertEqual(guess_category("North Korea Suspected in $351 Million Bitget Crypto Heist",
                                        "The breach at the exchange was traced to a supplier.", False), Category.breach)
        self.assertEqual(guess_category("OpenAI apologizes for agents breaching Australian government websites without authorization",
                                        "The breach involved AI agents.", False), Category.breach)

    def test_a_breach_in_passing_in_the_lead_is_not(self):
        self.assertEqual(
            guess_category("Zero Trust for AI Agents Starts With Fixing Zero Visibility", "A breach is inevitable, experts say.", False),
            Category.news,
        )


class Vulnerability(unittest.TestCase):
    def test_a_trend_piece_is_research_or_news(self):
        # SecurityWeek, 2026-09-30: about vulnerability discovery in general, no flaw, product or CVE.
        title = "Google: AI Is Changing the Pace and Profile of Vulnerability Discovery"
        self.assertEqual(guess_category(title, "", False), Category.research)
        self.assertEqual(guess_category(title, "", False, trends=False), Category.vulnerability)  # the old rule
        self.assertEqual(guess_category("Microsoft expands bug bounty for Copilot", "", False), Category.news)
        self.assertEqual(guess_category("The state of ransomware in 2026", "", False), Category.ransomware)

    def test_a_specific_flaw_product_or_cve_stays_a_vulnerability(self):
        for title in (
            "Chrome, Firefox Updates Patch Over 100 Vulnerabilities",
            "Attackers Exploit Zimbra Flaw to Deploy Web Shells and Harvest Authentication Secrets",
            "WatchGuard Patches Critical Fireware OS Code Injection Vulnerability",
        ):
            self.assertEqual(guess_category(title, "", False), Category.vulnerability, title)
        # A CVE makes it specific even in a trend-worded title.
        self.assertEqual(guess_category("Exploitation of CVE-2026-76504 is changing the SD-WAN landscape", "", True), Category.vulnerability)


class RulesAndOverrides(unittest.TestCase):
    """Categories come from the rules, the trend pre-filter and manual overrides only; the summary
    call's verdicts are logged, never used (2026-09-30)."""

    def test_specific_flaws_stay_vulnerability(self):
        for title, has_cve in (
            ("Attackers Exploit Zimbra Flaw to Deploy Web Shells and Harvest Authentication Secrets", True),
            ("WatchGuard Patches Critical Fireware OS Code Injection Vulnerability", True),
            ("TeamViewer urges users to patch severe flaws “as soon as possible”", True),
            ("Cisco warns of new SD-WAN zero-day exploited in attacks", True),
            ("WatchGuard Patches Critical Fireware OS Code Injection Vulnerability", False),
        ):
            self.assertEqual(guess_category(title, "", has_cve), Category.vulnerability, title)

    def test_misfires_are_manual_overrides(self):
        from app.tagging import CATEGORY_OVERRIDES

        # The rules call this Vulnerability; a misfire is a manual override.
        self.assertEqual(guess_category("Google: Vulnerability disclosures double to 10,000 per month as AI fuels exploitation", "", False),
                         Category.vulnerability)
        for value in CATEGORY_OVERRIDES.values():
            Category(value)  # every override names a real category


if __name__ == "__main__":
    unittest.main()
