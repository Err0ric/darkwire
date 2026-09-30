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


class SpecificVulnerability(unittest.TestCase):
    """The summary call's verdict (facts specific_vulnerability) decides a row with no CVE."""

    GENERAL = (
        "Google: Vulnerability disclosures double to 10,000 per month as AI fuels exploitation",
        "Google: AI Is Changing the Pace and Profile of Vulnerability Discovery",
    )
    SPECIFIC = (
        "Attackers Exploit Zimbra Flaw to Deploy Web Shells and Harvest Authentication Secrets",
        "WatchGuard Patches Critical Fireware OS Code Injection Vulnerability",
        "TeamViewer urges users to patch severe flaws “as soon as possible”",
    )

    def test_general_pieces_are_not_vulnerability(self):
        for title in self.GENERAL:
            self.assertEqual(guess_category(title, "", False, specific=False), Category.research, title)
        # Before the call (specific unknown), the keyword pre-filter still catches the trend wording.
        self.assertEqual(guess_category(self.GENERAL[1], "", False), Category.research)

    def test_specific_flaws_stay_vulnerability(self):
        for title in self.SPECIFIC:
            self.assertEqual(guess_category(title, "", False, specific=True), Category.vulnerability, title)
            self.assertEqual(guess_category(title, "", False), Category.vulnerability, title)  # not asked yet
            # A CVE on the row is enough whatever the call says.
            self.assertEqual(guess_category(title, "", True, specific=False), Category.vulnerability, title)

    def test_row_943_and_the_cve_rows(self):
        # Row 943 (2026-09-30): the call said the main subject is not one flaw.
        self.assertNotEqual(
            guess_category("Google: Vulnerability disclosures double to 10,000 per month as AI fuels exploitation", "", False, specific=False),
            Category.vulnerability,
        )
        # Zimbra, TeamViewer and Cisco SD-WAN rows carry CVEs; WatchGuard's call names the flaw.
        for title in ("Attackers Exploit Zimbra Flaw to Deploy Web Shells and Harvest Authentication Secrets",
                      "TeamViewer urges users to patch severe flaws “as soon as possible”",
                      "Cisco warns of new SD-WAN zero-day exploited in attacks"):
            self.assertEqual(guess_category(title, "", True, specific=False), Category.vulnerability, title)
        self.assertEqual(guess_category("WatchGuard Patches Critical Fireware OS Code Injection Vulnerability", "", False, specific=True),
                         Category.vulnerability)

    def test_an_organization_compromised_through_a_flaw_is_a_breach(self):
        # Row 829 (2026-09-30).
        title = "Bitget Says Attacker Exploited Third-Party Security Product Flaw to Steal $388M"
        self.assertEqual(guess_category(title, "", False, specific=False, compromised=True), Category.breach)
        self.assertEqual(guess_category(title, "", False, specific=True, compromised=True), Category.breach)

    def test_other_rules_still_apply_without_a_specific_flaw(self):
        self.assertEqual(guess_category("Ransomware gangs exploit flaws faster than ever", "", False, specific=False), Category.ransomware)
        self.assertEqual(guess_category("Patch Tuesday fatigue is real", "", False, specific=False), Category.news)


if __name__ == "__main__":
    unittest.main()
