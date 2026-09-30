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


if __name__ == "__main__":
    unittest.main()
