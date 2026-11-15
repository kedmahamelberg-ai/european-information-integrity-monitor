"""Check the current DOI archive, bilingual releases, and article text."""
import datetime as dt
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location(
    "collect_government_news", Path(__file__).resolve().parents[1] / "scripts/collect_government_news.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def card(number, title, day="14/11/2026"):
    return (f'<a href="/press-release/2026/{number.lower()}" class="flex flex-col lg:flex-row">'
            f'<span>{day}</span><span>{number}</span><span>{title}</span></a>')


ARTICLE = '<html><main><div class="flex flex-col items-stretch justify-start gap-2 pb-5"><p>Official government communication with enough article text for a full classification.</p></div></main></html>'


class MaltaCollectorTests(unittest.TestCase):
    def setUp(self):
        self.country = {"iso2": "MT", "name": "Malta", "url": collector.MALTA_ARCHIVE}
        self.start = dt.datetime(2026, 11, 9, tzinfo=collector.MALTA)
        self.end = dt.datetime(2026, 11, 15, 23, tzinfo=collector.MALTA)

    def test_paginates_prefers_english_and_reads_full_article(self):
        first = ('<html>' + card("PR261925", "Maltese title") +
                 '<a href="/en/search/press-releases?p=2">2</a></html>')
        second = '<html>' + card("PR261925EN", "English title") + card("PR261926", "Other title") + '</html>'
        with patch.object(collector, "fetch_malta_html", side_effect=[first, second, ARTICLE, ARTICLE]) as fetch:
            items, home = collector.discover_malta(self.country, self.start, self.end)
        self.assertEqual(len(items), 2)
        self.assertEqual(home, self.country["url"])
        self.assertEqual(items[0]["title"], "English title")
        self.assertEqual(items[0]["published_date"], "2026-11-14")
        self.assertIn("pr261925en", items[0]["url"])
        self.assertIn("Official government communication", items[0]["text"])
        self.assertEqual(fetch.call_count, 4)

    def test_rejects_incomplete_article(self):
        with patch.object(collector, "fetch_malta_html", side_effect=['<html>'+card("PR261925EN", "English title")+'</html>', '<html>No article</html>']):
            with self.assertRaisesRegex(RuntimeError, "usable article text"):
                collector.discover_malta(self.country, self.start, self.end)

    def test_rejects_nonofficial_url(self):
        with self.assertRaisesRegex(RuntimeError, "left the official"):
            collector.fetch_malta_html("https://example.com/other")


if __name__ == "__main__": unittest.main()
