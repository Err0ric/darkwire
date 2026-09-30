"""Stale-source safeguard (app/advisories.py): the fix and affected sentences of an advisory.
The read / re-read schedule runs against Postgres in test_db_article_cves.py.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app import advisories

# CISA's MikroTik RouterOS advisory (row 873), as first read and as corrected (2026-09-30).
FIRST = (
    "MikroTik RouterOS contains an integer underflow in the web management service.\n"
    "Successful exploitation could allow remote code execution.\n"
    "The following versions of MikroTik RouterOS are affected: RouterOS <7.24.\n"
    "MikroTik recommends users update RouterOS to version 7.23 or later.\n"
    "CISA recommends users minimize network exposure."
)
CORRECTED = FIRST.replace("7.23 or later", "7.24 or later")


class FixSentences(unittest.TestCase):
    def test_only_fix_and_affected_sentences_with_a_number(self):
        self.assertEqual(
            advisories.fix_sentences(FIRST),
            ["The following versions of MikroTik RouterOS are affected: RouterOS <7.24.",
             "MikroTik recommends users update RouterOS to version 7.23 or later."],
        )

    def test_a_corrected_fix_version_changes_the_digest_other_edits_do_not(self):
        self.assertNotEqual(advisories.digest(FIRST), advisories.digest(CORRECTED))
        reworded = FIRST.replace("CISA recommends users minimize network exposure.", "CISA urges minimizing exposure.")
        self.assertEqual(advisories.digest(FIRST), advisories.digest(reworded))
        self.assertEqual(advisories.digest(FIRST), advisories.digest(FIRST.replace("\n", "\n\n  ")))


if __name__ == "__main__":
    unittest.main()
