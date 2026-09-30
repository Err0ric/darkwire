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


if __name__ == "__main__":
    unittest.main()
