"""Version ranges (app/versions.py): a stated fix inside the stated affected range.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app import versions

# Row 873's model summary (the CISA advisory for MikroTik RouterOS).
MIKROTIK = (
    "MikroTik RouterOS versions before 7.24 contain an integer underflow in the web management service's HTTP "
    "request handling that allows unauthenticated attackers to achieve remote code execution or denial of service "
    "with a single crafted request. MikroTik recommends updating to version 7.23 or later."
)


class Versions(unittest.TestCase):
    def test_conflicts(self):
        self.assertTrue(versions.conflict("RouterOS <7.24", "7.23 or later"))
        self.assertTrue(versions.conflict("versions 5.5.2 and prior", "5.5.1"))
        self.assertFalse(versions.conflict("PowerChute Serial Shutdown version 1.5 and prior", "1.6"))
        self.assertFalse(versions.conflict("ABB Ability Edgenius >=3.2.0.0|<3.2.4.1", "3.2.4.1"))
        self.assertFalse(versions.conflict("Grav CMS 1.7.43", "2.0.0-beta.2"))  # no range stated

    def test_one_bound_per_release_line(self):
        self.assertFalse(versions.conflict("1.6.x before 1.6.16 and 1.7.x before 1.7.1", "1.6.16 and 1.7.1"))
        self.assertTrue(versions.conflict("1.6.x before 1.6.16 and 1.7.x before 1.7.1", "1.6.15"))

    def test_summary_conflict_and_strip(self):
        self.assertTrue(versions.summary_conflict(MIKROTIK))
        # Whole sentences go, so what is left still reads (row 933, 2026-09-30); none left: empty.
        row_933 = ("CISA warns of a pre-authentication integer underflow in MikroTik RouterOS that allows unauthenticated "
                   "attackers to achieve remote code execution as root or denial of service. Affected versions are below "
                   "7.24; the vendor recommends updating to version 7.23 or later.")
        self.assertEqual(versions.strip(row_933), row_933.split(". ")[0] + ".")
        self.assertEqual(versions.strip(MIKROTIK), "")
        self.assertFalse(versions.summary_conflict("Roundcube fixed the flaw in 1.6.16; versions before 1.6.16 are affected."))
        self.assertFalse(versions.summary_conflict("Versions before 7.24 are affected. Update to 7.24."))

    def test_branches(self):
        self.assertEqual(
            versions.branches("7.24 stable, 7.23.5 long-term", ""),
            [{"version": "7.24", "branch": "stable"}, {"version": "7.23.5", "branch": "long-term"}],
        )
        self.assertEqual(
            versions.branches("7.24 and 7.23.5", "fixed in 7.24 (stable) and 7.23.5 (long-term)"),
            [{"version": "7.24", "branch": "stable"}, {"version": "7.23.5", "branch": "long-term"}],
        )
        self.assertEqual(versions.branches("7.23 or later", "update to 7.23 or later"), [])


if __name__ == "__main__":
    unittest.main()
