"""The content rules for article facts (app/facts.py recheck), from real rows of the 2026-09-30
batch dry run and the first live rows.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app.facts import affected_problem, fixed_problem, poc_problem, recheck

POC_FAIL = {
    114: ("The researchers confirmed on September 14 that their proof of concept no longer worked.", None),
    115: ("He published on September 24 anyway, when OnePlus had released no fix.", None),
    125: ("Aikido showed how a holder turns it into a way to commit code, using GitLab's own merge request by email feature", None),
    796: ("Viettel Security, whose researchers reported the vulnerability to Microsoft, disclosed technical details.", "CVE-2026-65660"),
    882: ("VUSec's proof-of-concept showed that stale predictions survive code reuse", "CVE-2026-64507"),
    883: ("As a proof-of-concept, two end-to-end exploits have been devised against the Linux kernel that can be used to leak "
          "and recover the root password hash within minutes from a fully patched Intel system with default protections enabled.", None),
    884: ("The researchers' proof-of-concept showed that stale branch entries persist in SpiderMonkey on Intel processors long "
          "enough to be reused.", None),
    # The row displays CVE-2026-88772; the quote is about its sibling CVE-2026-88771.
    906: ("The disclosure comes a day after the preemptive exposure management company released a proof-of-concept (PoC) for "
          "CVE-2026-88771", "CVE-2026-88772"),
}

POC_PASS = {
    132: ("DepthFirst released exploit code targeting Ubuntu 26.04.", None),
    138: ("Ressl published a detailed write-up when the fix shipped, along with a proof-of-concept and a self-contained test lab.",
          "CVE-2026-87902"),
    142: ("A zero-day proof-of-concept tool that stops Microsoft Defender from installing platform and signature updates by "
          "filling all available disk space was published on GitHub on September 19.", None),
    150: ("security researcher Patrick Wardle has shown in a proof-of-concept released on September 21", None),
    792: ("the full exploit markup is now public", "CVE-2026-65660"),
    874: ("CISA discovered a public proof of concept as authored by indoushka and reported it to VIVOTEK.", "CVE-2026-22755"),
}


class PublicPoc(unittest.TestCase):
    def test_real_quotes_that_fail(self):
        for row, (quote, cve) in POC_FAIL.items():
            with self.subTest(row=row):
                self.assertIsNotNone(poc_problem(quote, cve), quote)

    def test_real_quotes_that_pass(self):
        for row, (quote, cve) in POC_PASS.items():
            with self.subTest(row=row):
                self.assertIsNone(poc_problem(quote, cve), quote)

    def test_reasons(self):
        self.assertEqual(poc_problem(POC_FAIL[114][0], None), "does not say it is public")
        self.assertEqual(poc_problem("A proof-of-concept was not published.", None), "negated")
        self.assertEqual(poc_problem(POC_FAIL[906][0], "CVE-2026-88772"), "about another CVE (CVE-2026-88771)")
        self.assertIsNone(poc_problem(POC_FAIL[906][0], "CVE-2026-88771"))


class FixedAndAffected(unittest.TestCase):
    def test_fixed_must_be_a_version(self):
        self.assertIsNone(fixed_problem("9.5.1"))  # row 6
        for ok in ("1.6.16 and 1.7.1", "2.0.0-beta.2", "Linux 6.18.51, 7.2.5, and 7.3-rc1", "KB5063878",
                   "transports/v2.1.0", "release 7.8", "build 26100"):
            self.assertIsNone(fixed_problem(ok), ok)
        # Row 91: a product with a major version is not a fixed version (major.minor at least).
        for bad in ("OpenPLC v4", "version 7", "August 11 patch", "Linux kernel", "the latest release"):
            self.assertIsNotNone(fixed_problem(bad), bad)

    def test_affected_must_be_a_product(self):
        self.assertIsNone(affected_problem("Linux Kernel"))  # row 799
        for ok in ("SharePoint Server 2016, 2019, and Subscription Edition", "Citrix NetScaler ADC and NetScaler Gateway",
                   "RouterOS <7.24"):
            self.assertIsNone(affected_problem(ok), ok)
        for row, bad in (
            (17, "10.2 million customers"),
            (836, "telecommunications organizations, universities, medical nonprofits, intergovernmental organizations, "
                  "and government contractors"),
            (855, "2.76 million living individuals and 294,000 deceased individuals"),
        ):
            with self.subTest(row=row):
                self.assertIsNotNone(affected_problem(bad), bad)


class Consistency(unittest.TestCase):
    def test_76_web_domains_are_not_a_product(self):
        self.assertIsNotNone(affected_problem("Radaris.com and more than a dozen other data broker domains"))

    def test_873_a_fix_inside_the_affected_range_drops_both(self):
        # The CISA advisory for MikroTik RouterOS (row 873): affected below 7.24, "fixed" 7.23 or later.
        stored = {
            "affected": {"text": "RouterOS <7.24", "quote": "The following versions of MikroTik RouterOS are affected: - RouterOS <7.24 (CVE-2026-84411)"},
            "fixed": {"version": "7.23 or later", "quote": "MikroTik recommends users update RouterOS to version 7.23 or later."},
        }
        kept, removed = recheck(stored, "CVE-2026-84411")
        self.assertEqual(kept, {})
        self.assertEqual(sorted(k for k, _ in removed), ["affected", "fixed"])

    def test_separate_release_branches_keep_both_with_labels(self):
        stored = {
            "affected": {"text": "RouterOS <7.24", "quote": "RouterOS versions below 7.24 are affected."},
            "fixed": {"version": "7.24 stable, 7.23.5 long-term",
                      "quote": "MikroTik fixed the flaw in 7.24 stable, 7.23.5 long-term."},
        }
        kept, removed = recheck(stored, None)
        self.assertEqual(removed, [])
        self.assertEqual(kept["fixed"]["branches"], [{"version": "7.24", "branch": "stable"}, {"version": "7.23.5", "branch": "long-term"}])
        self.assertIn("affected", kept)

    def test_fixes_per_line_are_not_a_conflict(self):
        # Row 30 (Roundcube): one bound per release line, one fix per line.
        stored = {
            "affected": {"text": "Roundcube Webmail versions 1.6.x before 1.6.16 and 1.7.x before 1.7.1", "quote": "q"},
            "fixed": {"version": "1.6.16 and 1.7.1", "quote": "q"},
        }
        self.assertEqual(recheck(stored)[1], [])


class Recheck(unittest.TestCase):
    def test_906_loses_its_poc_and_keeps_the_rest(self):
        stored = {
            "affected": {"text": "Citrix NetScaler ADC and NetScaler Gateway", "quote": "Citrix NetScaler ADC and NetScaler Gateway contain..."},
            "public_poc": {"quote": POC_FAIL[906][0]},
            "exploited_in_wild": {"quote": "...has come under active exploitation in the wild"},
        }
        kept, removed = recheck(stored, "CVE-2026-88772")
        self.assertEqual(set(kept), {"affected", "exploited_in_wild"})
        self.assertEqual(removed, [("public_poc", "about another CVE (CVE-2026-88771)")])


if __name__ == "__main__":
    unittest.main()
