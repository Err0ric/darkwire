"""Summary output checks (app/summaries.py): bare domains are defanged, full URLs rejected.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app.summaries import check_workaround, defang, review_summary

# Row 76's second output (2026-09-27), completed: it names the site the story is about.
RADARIS = (
    "Data broker Radaris lost control of radaris.com and over a dozen related domains in a lawsuit "
    "alleging violations of New Jersey's Daniel's Law."
)


class BareDomains(unittest.TestCase):
    def test_bare_domain_is_defanged_not_rejected(self):
        text, why = review_summary(RADARIS)
        self.assertEqual(why, "ok")
        self.assertIn("radaris[.]com", text)
        self.assertNotIn("radaris.com", text)

    def test_subdomains_and_www_defang_every_dot(self):
        self.assertEqual(defang("see security.paloaltonetworks.com today"), "see security[.]paloaltonetworks[.]com today")
        self.assertEqual(defang("www.example.org."), "www[.]example[.]org.")
        self.assertEqual(defang("Radaris.com"), "Radaris[.]com")

    def test_products_are_not_domains(self):
        for product in ("ASP.NET Core", "Node.js", "version 6.7.2", "the .NET runtime"):
            self.assertEqual(defang(product), product)


class FullUrls(unittest.TestCase):
    def test_scheme_is_rejected(self):
        self.assertEqual(review_summary("Radaris lost its domains; details at https://radaris.com today.")[1], "format")
        self.assertEqual(review_summary("Radaris lost its domains; details at http://example.org.")[1], "format")

    def test_domain_with_a_path_is_rejected(self):
        self.assertEqual(review_summary("Radaris lost its domains, per radaris.com/legal/notice this week.")[1], "format")
        self.assertEqual(review_summary("The advisory at www.example.com/advisory lists affected builds.")[1], "format")

    def test_workarounds_still_reject_any_domain(self):
        self.assertIsNone(check_workaround("Block traffic to example.com at the proxy."))


# Row 930's declined output (2026-09-30, "fix claim"): the vendor is the one who fixed it.
CISCO = ("Cisco released updates for a critical zero-day in Catalyst SD-WAN Manager (CVE-2026-76504) that "
         "attackers actively exploit to gain admin privileges.")
CISCO_ARTICLE = "Cisco has released security updates to address the flaw, which is being exploited in attacks."


class FixClaims(unittest.TestCase):
    def test_the_vendor_as_the_one_who_fixed_it_is_attributed(self):
        self.assertEqual(review_summary(CISCO, material=CISCO_ARTICLE), (CISCO, "ok"))
        for text in (
            "WatchGuard patched a critical code injection vulnerability in Fireware OS used by thousands of firewalls worldwide.",
            "Kiteworks patched a critical vulnerability in an unnamed feature affecting a small share of its customers.",
            "The vendor has patched the flaw that let attackers read files from exposed management interfaces remotely.",
        ):
            self.assertEqual(review_summary(text, material=CISCO_ARTICLE)[1], "ok", text)

    def test_unattributed_or_speculative_claims_still_go(self):
        for text in (
            "The flaw was patched in version 20.12, and attackers exploited it to gain admin privileges on exposed SD-WAN Manager instances.",
            "A fix is available for the flaw, which attackers exploit to gain admin privileges on exposed SD-WAN Manager instances.",
        ):
            self.assertEqual(review_summary(text, material=CISCO_ARTICLE), (None, "fix claim"), text)

    def test_an_attributed_claim_the_articles_do_not_back_goes(self):
        self.assertEqual(review_summary(CISCO, material="Attackers exploit a Cisco zero-day.")[1], "fix claim")


if __name__ == "__main__":
    unittest.main()
