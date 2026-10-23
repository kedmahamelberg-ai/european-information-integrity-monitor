"""Check Malta's dated SharePoint archive and bilingual release handling."""
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


def release(number, title, date="2026-10-21T22:00:00Z", day="22"):
    return {"Id": 1, "FileSystemObjectType": 0, "Gov_PublicationNumber": number,
            "FileRef": f"/en/Government/DOI/Press Releases/Pages/2026/10/{day}/{number}.aspx",
            "Title": title, "ArticleStartDate": date,
            "Gov_MainContent": "<p>Official government communication with enough article text for a full classification.</p>"}


class MaltaCollectorTests(unittest.TestCase):
    def setUp(self):
        self.country = {"iso2": "MT", "name": "Malta", "url": "https://www.gov.mt/en/Government/DOI/Press%20Releases/Pages/default.aspx"}
        self.start = dt.datetime(2026, 10, 22, 0, tzinfo=collector.MALTA)
        self.end = dt.datetime(2026, 10, 22, 23, tzinfo=collector.MALTA)

    def test_paginates_and_prefers_english_release(self):
        next_url = collector.MALTA_API + "?$skiptoken=next"
        pages = [{"value": [release("PR261776", "Maltese title")], "odata.nextLink": next_url},
                 {"value": [release("PR261776en", "English title"), release("PR261777", "Other title")]}]
        with patch.object(collector, "fetch_malta_json", side_effect=pages) as fetch:
            items, home = collector.discover_malta(self.country, self.start, self.end)
        self.assertEqual(len(items), 2)
        self.assertEqual(home, self.country["url"])
        self.assertEqual(items[0]["title"], "English title")
        self.assertEqual(items[0]["publication_precision"], "day")
        self.assertEqual(items[0]["published_date"], "2026-10-22")
        self.assertIn("PR261776en.aspx", items[0]["url"])
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("ArticleStartDate+ge+datetime", fetch.call_args_list[0].args[0])

    def test_rejects_mismatched_publication_date(self):
        with patch.object(collector, "fetch_malta_json", return_value={"value": [release("PR261778", "Wrong day", day="23")]}):
            with self.assertRaisesRegex(RuntimeError, "date differs"):
                collector.discover_malta(self.country, self.start, self.end)

    def test_rejects_nonofficial_pagination_url(self):
        with self.assertRaisesRegex(RuntimeError, "left the official API"):
            collector.fetch_malta_json("https://example.com/other")


if __name__ == "__main__":
    unittest.main()
