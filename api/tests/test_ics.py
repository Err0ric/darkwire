"""CISA ICS advisory summaries (app/ics.py): built from stored fields only, never the model.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app.ics import PREFIX, ics_summary, is_ics_advisory
from app.models import PatchStatus, Severity

# Row 81 in production: CISA's advisory, one CVE (NVD: Rejected, so no score), fix unverified.
ROW_81 = dict(
    headline="Siemens Mendix Runtime (Update A)",
    url="https://www.cisa.gov/news-events/ics-advisories/icsa-26-209-02",
    cve_count=1,
    cvss=None,
    severity=None,
    patch=PatchStatus.unverified,
)


class IcsSummary(unittest.TestCase):
    def test_row_81(self):
        r = ROW_81
        self.assertTrue(is_ics_advisory(r["url"]))
        self.assertEqual(
            ics_summary(r["headline"], r["cve_count"], r["cvss"], r["severity"], r["patch"]),
            "CISA industrial control systems advisory for Siemens Mendix Runtime (update A), covering 1 CVE.",
        )

    def test_row_81_once_enriched(self):
        r = ROW_81
        self.assertEqual(
            ics_summary(r["headline"], 3, 9.8, Severity.critical, PatchStatus.patched),
            "CISA industrial control systems advisory for Siemens Mendix Runtime (update A), covering 3 CVEs,"
            " the highest rated CVSS 9.8 (Critical). Vendor data lists a fix.",
        )

    def test_one_scored_cve_without_a_fix(self):
        self.assertEqual(
            ics_summary("Bransys ELD", 1, 7.5, "high", "no_fix"),
            "CISA industrial control systems advisory for Bransys ELD, covering 1 CVE rated CVSS 7.5 (High)."
            " Vendor data lists no fix yet.",
        )

    def test_nothing_missing_is_written_out(self):
        text = ics_summary("Baicells Nova 430H", 0, None, None, None)
        self.assertEqual(text, "CISA industrial control systems advisory for Baicells Nova 430H.")
        for word in ("unknown", "unverified", "None", "null", "0 CVE"):
            self.assertNotIn(word, ics_summary("X Y", 0, None, Severity.none, PatchStatus.unverified))
        self.assertTrue(text.startswith(PREFIX))

    def test_only_advisory_pages(self):
        self.assertTrue(is_ics_advisory("https://www.cisa.gov/news-events/ics-medical-advisories/icsma-26-100-01"))
        self.assertFalse(is_ics_advisory(
            "https://www.cisa.gov/resources-tools/resources/ics-advisories/considerations-critical-infrastructure-operators"
        ))
        self.assertFalse(is_ics_advisory("https://www.cisa.gov/news-events/alerts/2026/09/29/cisa-adds-one-known-exploited-vulnerability-catalog"))
        self.assertFalse(is_ics_advisory(None))


if __name__ == "__main__":
    unittest.main()
