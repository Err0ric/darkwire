"""Vendor tagging (app/tagging.py VendorMatcher) with the seeded vendor list: a platform in a title
does not make its maker the vendor when another vendor or product is named.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app.models import Vendor
from app.seed import VENDORS
from app.tagging import VendorMatcher

MATCHER = VendorMatcher([Vendor(id=i, slug=v["slug"], name=v["name"], aliases=v["aliases"]) for i, v in enumerate(VENDORS)])
SLUG = {i: v["slug"] for i, v in enumerate(VENDORS)}


def vendor(title: str, excerpt: str = "") -> str | None:
    found = MATCHER.match(title, excerpt)
    return SLUG.get(found) if found is not None else None


class Platforms(unittest.TestCase):
    def test_the_signal_row(self):
        # 2026-09-30: tagged Apple from "iOS".
        self.assertEqual(vendor("Signal adds encrypted local backup support to iOS, desktop apps"), "signal")

    def test_a_platform_alone_is_still_its_makers(self):
        self.assertEqual(vendor("iOS 26.1 fixes two actively exploited WebKit flaws"), "apple")
        self.assertEqual(vendor("Critical Windows flaw exploited in attacks"), "microsoft")
        self.assertEqual(vendor("New Android malware steals banking credentials"), "google")

    def test_another_product_beats_the_platform(self):
        self.assertEqual(vendor("Chrome for Android update fixes zero-day"), "google")
        self.assertEqual(vendor("Firefox on Windows gets a sandbox fix"), "mozilla")
        self.assertEqual(vendor("Cisco IOS XE flaw exploited"), "cisco")

    def test_signal_the_word_is_not_signal_the_app(self):
        self.assertIsNone(vendor("Ransomware attacks send a strong signal to hospitals"))



class Arista(unittest.TestCase):
    # 2026-10-22/23 (prod 1871, 1891, 1908): three VeloCloud zero-day rows, untagged, never merged.
    TITLES = [
        "Arista patches new VeloCloud Orchestrator zero-day exploited in attacks",
        "Arista Warns of Critical VeloCloud SQL Injection Zero-Day Exploited in Attacks",
        "Attackers Exploit Third VeloCloud Orchestrator Zero-Day in Four Months",
    ]

    def test_velocloud_rows_are_arista(self):
        for t in self.TITLES:
            self.assertEqual(vendor(t), "arista")

    def test_velocloud_zero_day_rows_merge_by_title(self):
        from datetime import UTC, datetime, timedelta

        from app import dedupe

        arista = next(i for i, s in SLUG.items() if s == "arista")
        t = datetime(2026, 10, 22, 17, tzinfo=UTC)
        for i, a in enumerate(self.TITLES):
            for b in self.TITLES[i + 1:]:
                self.assertTrue(dedupe.title_merge_ok(a, t, arista, b, t + timedelta(hours=16), arista, MATCHER), (a, b))
        # The two-story KEV piece is not a zero-day title: it stays out.
        two = "CISA Flags Two Actively Exploited Critical Flaws in Collabora Online and Arista VeloCloud"
        self.assertFalse(dedupe.title_merge_ok(self.TITLES[0], t, arista, two, t, arista, MATCHER))
        # The vendor's name alone is not a product: two unrelated Arista zero-days do not merge.
        self.assertFalse(dedupe.title_merge_ok("Arista EOS zero-day exploited", t, arista, "Arista patches zero-day in CloudVision", t, arista, MATCHER))


if __name__ == "__main__":
    unittest.main()
