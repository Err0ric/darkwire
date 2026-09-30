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


if __name__ == "__main__":
    unittest.main()
