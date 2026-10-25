"""Accept the ministry's numeric article paths without widening URL scope."""
import datetime as dt
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location(
    "georgia_collector", Path(__file__).resolve().parents[1] / "scripts/collect_government_news.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class GeorgiaCollectorTests(unittest.TestCase):
    country = {"iso2": "GE", "name": "Georgia", "url": "https://mfa.gov.ge/news"}
    start = dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)

    def discover(self, slug):
        row = {"publishDate": "2026-10-22T12:00:00+04:00", "slug": slug, "title": "Official statement"}
        page = {"content": {"page": 1, "pageCount": 1, "total": 1, "count": 1, "data": [row]}}
        with patch.object(collector, "fetch_georgia_page", return_value=page):
            return collector.discover_georgia(self.country, self.start, self.end)[0]

    def test_numeric_and_named_paths_keep_the_exact_official_url(self):
        for slug in ("320426", "847948-batumshi-saqartvelosa"):
            with self.subTest(slug=slug):
                items = self.discover(slug)
                self.assertEqual(items[0]["url"], "https://mfa.gov.ge/news/" + slug)
                self.assertEqual(items[0]["published_at"], "2026-10-22T08:00:00+00:00")

    def test_rejects_paths_that_could_leave_the_article_section(self):
        for slug in ("", None, "320426/../../other", "https://example.com/320426", "320426?redirect=other"):
            with self.subTest(slug=slug), self.assertRaisesRegex(RuntimeError, "Unexpected Georgian article slug"):
                self.discover(slug)


if __name__ == "__main__":
    unittest.main()
