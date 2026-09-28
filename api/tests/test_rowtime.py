"""Row time rules (app/rowtime.py): a row's time is its earliest news source, never a CVE, KEV
or NVD date, and a sync moves it back only when a news source genuinely published earlier.

    cd api && python -m unittest discover -s tests
"""

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from app import rowtime
from app.fix_row_times import parse_rows, planned

THN = datetime(2026, 9, 26, 11, 46, 40, tzinfo=UTC)  # The Hacker News, the earliest article
BC = datetime(2026, 9, 26, 19, 3, 34, tzinfo=UTC)  # BleepingComputer, later
KEV_STAMP = datetime(2026, 9, 27, 16, 55, 29, 18750, tzinfo=UTC)  # a non-news moment
CISA = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def row(at, kind, *published, id=1):
    return SimpleNamespace(
        id=id, headline="Attackers Bypass WAFs to Exploit Oracle PeopleSoft Flaw", last_event_at=at,
        last_event_kind=kind, sources=[SimpleNamespace(published_at=p) for p in published],
    )


class RowTime(unittest.TestCase):
    def test_news_time_is_the_earliest_source(self):
        self.assertEqual(rowtime.news_time([BC, None, THN]), THN)
        self.assertIsNone(rowtime.news_time([None]))

    def test_a_later_source_does_not_move_the_row(self):
        self.assertEqual(rowtime.after_source_joins(THN, BC), THN)
        self.assertEqual(rowtime.after_source_joins(THN, None), THN)

    def test_an_earlier_source_moves_it_back(self):
        self.assertEqual(rowtime.after_source_joins(BC, THN), THN)

    def test_set_row_time_logs_old_new_and_reason(self):
        item = row(BC, "published", THN, BC)
        with self.assertLogs("app.rowtime", "INFO") as logs:
            self.assertTrue(rowtime.set_row_time(item, THN, "news source joined: The Hacker News"))
        self.assertEqual(item.last_event_at, THN)
        self.assertIn("2026-09-26T19:03:34+00:00 -> 2026-09-26T11:46:40+00:00 (news source joined: The Hacker News)", logs.output[0])

    def test_no_change_no_log(self):
        item = row(THN, "published", THN, BC)
        with self.assertNoLogs("app.rowtime", "INFO"):
            self.assertFalse(rowtime.set_row_time(item, THN, "same"))


class TheCase(unittest.TestCase):
    """The row from the report: its time had been set to a non-news moment (a KEV "added"
    stamp at 16:55 on Sep 27) while its articles are from Sep 26. A news source joining must
    put it on its earliest article, and the one-off fix must plan exactly that."""

    def test_merge_puts_a_stamped_row_on_its_earliest_article(self):
        item = row(KEV_STAMP, "kev_added", THN)
        item.sources.append(SimpleNamespace(published_at=BC))  # BleepingComputer joins in a sync
        new = rowtime.news_time(s.published_at for s in item.sources)
        with self.assertLogs("app.rowtime", "INFO") as logs:
            rowtime.set_row_time(item, new, "news source joined: BleepingComputer")
        self.assertEqual((item.last_event_at, item.last_event_kind), (THN, "published"))
        self.assertIn("was a kev_added time", logs.output[0])

    def test_a_kev_date_is_never_the_row_time(self):
        # CISA's catalog date (midnight) before the article: the row takes the article's time.
        kev_row = row(datetime(2026, 9, 25, tzinfo=UTC), "kev_added", CISA, id=93)
        self.assertEqual([(i.id, new) for i, _, new, _ in planned([kev_row])], [(93, CISA)])

    def test_the_fix_leaves_correct_rows_alone(self):
        self.assertEqual(planned([row(THN, "published", THN, BC)]), [])

    def test_rows_option(self):
        self.assertIsNone(parse_rows(["fix_row_times", "--apply"]))
        self.assertEqual(parse_rows(["fix_row_times", "--rows", "79"]), [79])
        self.assertEqual(parse_rows(["fix_row_times", "--rows", "79,93", "--apply"]), [79, 93])


if __name__ == "__main__":
    unittest.main()
