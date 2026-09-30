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
            # Row 930's second model output (2026-09-30): "fixed" right after the vendor's verb.
            "Cisco Catalyst SD-WAN Manager has an API authentication bypass that attackers exploit. Cisco has released fixed software versions.",
        ):
            self.assertEqual(review_summary(text, material=CISCO_ARTICLE)[1], "ok", text)

    def test_unattributed_or_speculative_claims_still_go(self):
        for text in (
            "The flaw was patched in version 20.12, and attackers exploited it to gain admin privileges on exposed SD-WAN Manager instances.",
            "A fix is available for the flaw, which attackers exploit to gain admin privileges on exposed SD-WAN Manager instances.",
        ):
            self.assertEqual(review_summary(text, material=CISCO_ARTICLE), (None, "fix claim"), text)

    def test_no_workaround_is_not_a_workaround(self):
        # Row 930's third output (2026-09-30).
        first = ("Cisco Catalyst SD-WAN Manager contains a critical API authentication bypass flaw (CVE-2026-76504) "
                 "that attackers are actively exploiting to gain admin access.")
        said = first + " Fixed software releases are available; Cisco recommends immediate upgrade as no workaround exists."
        self.assertEqual(review_summary(said, material=CISCO_ARTICLE), (first, "ok"))
        # A clause that names a workaround still stays.
        kept = "Attackers exploit the flaw in SD-WAN Manager, and a patch is available alongside a workaround that restricts API access."
        self.assertEqual(review_summary(kept, material=CISCO_ARTICLE), (kept, "ok"))

    def test_an_attributed_claim_the_articles_do_not_back_goes(self):
        self.assertEqual(review_summary(CISCO, material="Attackers exploit a Cisco zero-day.")[1], "fix claim")


# Row 930's model output (2026-09-30): the second sentence is a passive fix claim from the news.
CISCO_PASSIVE = ("Cisco Catalyst SD-WAN Manager contains CVE-2026-76504, an API authentication bypass being actively "
                 "exploited in the wild. Fixed releases are available.")
CISCO_FIRST = CISCO_PASSIVE.split(" Fixed")[0]


class VendorBackedFixClaims(unittest.TestCase):
    def test_a_vendor_backed_passive_claim_is_attributed(self):
        self.assertEqual(
            review_summary(CISCO_PASSIVE, material=CISCO_ARTICLE + " Fixed releases are available.", vendor="Cisco"),
            (CISCO_FIRST + " Cisco says fixed releases are available.", "ok"),
        )
        # Clause by clause; a proper noun keeps its case.
        text, why = review_summary(
            "Attackers exploit an authentication bypass in NetScaler ADC, and NetScaler 14.1-73.37 fixes the flaw.",
            material="Citrix fixed the flaw in 14.1-73.37.", vendor="Citrix",
        )
        self.assertEqual((text, why), ("Attackers exploit an authentication bypass in NetScaler ADC, and Citrix says NetScaler 14.1-73.37 fixes the flaw.", "ok"))

    def test_without_vendor_backing_a_passive_news_claim_goes(self):
        self.assertEqual(review_summary(CISCO_PASSIVE, material=CISCO_ARTICLE + " Fixed releases are available."), (CISCO_FIRST, "ok"))

    def test_fix_vendor(self):
        from app.models import Item, ItemSource, PatchStatus, Source, Vendor
        from app.summaries import fix_vendor

        cisco = Vendor(id=1, slug="cisco", name="Cisco", domain="cisco.com")
        news = Source(id=1, name="BleepingComputer", feed_url="x", vendor_id=None)

        def row(url, text, status=PatchStatus.unverified):
            src = ItemSource(id=1, url=url, excerpt=text)
            src.source = news
            item = Item(id=930, headline="h", vendor=cisco, patch_status=status)
            item.sources = [src]
            return item

        self.assertIsNone(fix_vendor(row("https://www.bleepingcomputer.com/x", "Fixed releases are available.")))
        self.assertEqual(fix_vendor(row("https://sec.cloudapps.cisco.com/a", "Fixed releases are available.")), "Cisco")
        self.assertIsNone(fix_vendor(row("https://sec.cloudapps.cisco.com/a", "Cisco is investigating.")))
        self.assertEqual(fix_vendor(row("https://www.bleepingcomputer.com/x", "", PatchStatus.patched)), "Cisco")


class PatchedRows(unittest.TestCase):
    def test_unpatched_wording_goes_once_vendor_data_says_patched(self):
        # Row 747 (2026-09-30), written before Citrix's fixed builds reached NVD.
        said = "Two unpatched remote code execution zero-days in Citrix NetScaler ADC and Gateway appliances are under active exploitation."
        self.assertEqual(
            review_summary(said, patched=True),
            ("Two remote code execution zero-days in Citrix NetScaler ADC and Gateway appliances are under active exploitation.", "ok"),
        )
        self.assertEqual(review_summary("Unpatched NetScaler appliances are under attack by several groups this week.", patched=True)[0],
                         "NetScaler appliances are under attack by several groups this week.")
        two = said + " No patch is available yet for either flaw."
        self.assertEqual(review_summary(two, patched=True)[0], review_summary(said, patched=True)[0])
        # Without vendor fix data the wording stays.
        self.assertEqual(review_summary(said), (said, "ok"))


if __name__ == "__main__":
    unittest.main()
