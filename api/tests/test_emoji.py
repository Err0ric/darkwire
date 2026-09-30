"""Headlines never carry emoji (app/tagging.py strip_emoji, applied at ingest).

    cd api && python -m unittest discover -s tests
"""

import unittest

from app.tagging import strip_emoji


class StripEmoji(unittest.TestCase):
    def test_eff_headline(self):
        # EFF Deeplinks, Elsewhere rail (2026-09-30).
        self.assertEqual(strip_emoji("🧮 Hey Siri, How Do I Limit AI Data Access? | EFFector 38.17"),
                         "Hey Siri, How Do I Limit AI Data Access? | EFFector 38.17")

    def test_joined_sequences_flags_and_symbols(self):
        self.assertEqual(strip_emoji("Warning ⚠️ zero-day 👨‍💻 in 🇺🇸 agencies ✅"), "Warning zero-day in agencies")

    def test_other_characters_stay(self):
        for text in ("Café Wi‑Fi — “quoted” → 50% off™ © ® § €5", "Ransomware: 東京 hospital, Müller GmbH #1 & co. (v2.0)"):
            self.assertEqual(strip_emoji(text), text)


if __name__ == "__main__":
    unittest.main()
