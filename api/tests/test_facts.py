"""Article facts read with the summary (app/facts.py): kept only when quoted from the articles.

    cd api && python -m unittest discover -s tests
"""

import json
import unittest

from app import facts

MATERIAL = (
    "<article>\nTitle: MikroTik RouterOS flaw\n\n"
    "MikroTik RouterOS versions before 7.24 contain an integer underflow in the web service. "
    "A proof-of-concept exploit was published on GitHub on Monday. "
    "The company says version 7.24 fixes the issue. "
    "Researchers say attackers are already exploiting the flaw in the wild.\n</article>"
)


def out(**f) -> str:
    base = {
        "exploited_in_wild": {"stated": False, "quote": None},
        "public_poc": {"stated": False, "quote": None},
        "affected": {"text": None, "quote": None},
        "fixed": {"version": None, "quote": None},
    }
    base.update(f)
    return json.dumps({"summary": "MikroTik RouterOS has an integer underflow in its web service.", "facts": base})


class Facts(unittest.TestCase):
    def test_quoted_facts_are_kept(self):
        summary, stated = facts.parse(out(
            public_poc={"stated": True, "quote": "A proof-of-concept exploit was published on GitHub on Monday."},
            exploited_in_wild={"stated": True, "quote": "Researchers say attackers are already exploiting the flaw in the wild."},
            affected={"text": "RouterOS versions before 7.24", "quote": "MikroTik RouterOS versions before 7.24 contain an integer underflow in the web service."},
            fixed={"version": "7.24", "quote": "The company says version 7.24 fixes the issue."},
        ))
        self.assertTrue(summary.startswith("MikroTik"))
        found = facts.verify(stated, MATERIAL)
        self.assertEqual(set(found), {"public_poc", "exploited_in_wild", "affected", "fixed"})
        self.assertEqual(found["fixed"]["version"], "7.24")

    def test_a_quote_not_in_the_articles_is_dropped(self):
        _, stated = facts.parse(out(
            public_poc={"stated": True, "quote": "Exploit code for the bug is widely available online."},  # invented
            fixed={"version": "7.25", "quote": "The company says version 7.24 fixes the issue."},  # value not in quote
        ))
        self.assertEqual(facts.verify(stated, MATERIAL), {})

    def test_quote_matching_ignores_case_whitespace_and_quote_marks(self):
        _, stated = facts.parse(out(public_poc={"stated": True, "quote": "a  proof-of-concept exploit was PUBLISHED on GitHub on Monday."}))
        self.assertIn("public_poc", facts.verify(stated, MATERIAL.replace("Monday.", "“Monday.”")))

    def test_stated_false_or_urls_are_dropped(self):
        _, stated = facts.parse(out(
            public_poc={"stated": False, "quote": "A proof-of-concept exploit was published on GitHub on Monday."},
            fixed={"version": "https://example.com/7.24", "quote": "The company says version 7.24 fixes the issue."},
        ))
        self.assertEqual(facts.verify(stated, MATERIAL), {})

    def test_not_json_is_nothing(self):
        self.assertEqual(facts.parse("SKIP"), (None, {}))
        self.assertEqual(facts.parse(""), (None, {}))

    def test_the_schema_requires_every_key(self):
        props = facts.SCHEMA["properties"]["facts"]
        self.assertEqual(set(props["required"]), {"exploited_in_wild", "public_poc", "affected", "fixed"})
        self.assertFalse(facts.SCHEMA["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
