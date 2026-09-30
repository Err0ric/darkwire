"""Category rules (app/tagging.py guess_category): a breach is an incident, an explainer is not.

    cd api && python -m unittest discover -s tests
"""

import unittest

from app.models import Category
from app.tagging import guess_category


class Breach(unittest.TestCase):
    def test_an_explainer_is_research_or_news(self):
        # Row 922 (The Hacker News, 2026-09-30) was tagged BREACH from its first paragraph.
        self.assertEqual(
            guess_category("Know Your Enemy: Browser-Based Attack Techniques in 2026",
                           "Browser-based attacks are now a leading cause of breaches.", False),
            Category.research,
        )
        self.assertEqual(guess_category("Cloud security trends for CISOs", "Breaches are rising.", False), Category.news)
        self.assertEqual(guess_category("How to respond to a data breach", "", False), Category.news)

    def test_an_incident_is_a_breach(self):
        self.assertEqual(guess_category("Pentagon Personnel Agency Data Breach Impacts 3 Million People", "", False), Category.breach)
        self.assertEqual(
            guess_category("Labcorp to overhaul data security practices",
                           "The company suffered a breach that exposed data of 10.2 million customers.", False),
            Category.breach,
        )

    def test_incident_words_in_the_title_count(self):
        # Rows 25 and 896 (2026-09-30): "breach" only in the lead, the incident in the title.
        self.assertEqual(guess_category("North Korea Suspected in $351 Million Bitget Crypto Heist",
                                        "The breach at the exchange was traced to a supplier.", False), Category.breach)
        self.assertEqual(guess_category("OpenAI apologizes for agents breaching Australian government websites without authorization",
                                        "The breach involved AI agents.", False), Category.breach)

    def test_a_breach_in_passing_in_the_lead_is_not(self):
        self.assertEqual(
            guess_category("Zero Trust for AI Agents Starts With Fixing Zero Visibility", "A breach is inevitable, experts say.", False),
            Category.news,
        )


if __name__ == "__main__":
    unittest.main()
