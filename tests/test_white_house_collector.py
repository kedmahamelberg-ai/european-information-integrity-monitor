"""The U.S. benchmark must stay within the dated White House archive."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_government_news as collector


def card(day, slug):
    return (f'<li class="wp-block-post"><h2><a href="https://www.whitehouse.gov/'
            f'briefings-statements/2026/10/{slug}/">{slug}</a></h2>'
            f'<time datetime="2026-10-{day:02d}T12:00:00-04:00">October {day}</time></li>')


class WhiteHouseCollectorTest(unittest.TestCase):
    def setUp(self):
        self.source = next(x for x in collector.SOURCES if x["iso2"] == "US")
        self.start = dt.datetime(2026, 10, 4, tzinfo=collector.SOURCE_TIMEZONES["US"]).astimezone(dt.timezone.utc)
        self.end = dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc)

    def test_pagination_stops_after_launch_boundary_and_reads_body(self):
        pages = {
            self.source["url"]: (card(9, "security-statement") +
                                 '<link rel="next" href="https://www.whitehouse.gov/news/page/2/">'),
            self.source["url"] + "page/2/": card(5, "fire-prevention") + card(2, "before-launch"),
        }
        body = b'<div class="wp-block-post-content"><p>Official statement about public safety with sufficient complete body text for classification.</p></div>'

        def fetch(url, **_):
            return url, (pages.get(url) or body).encode() if url in pages else body

        with patch.object(collector, "fetch", side_effect=fetch) as mocked:
            items, home = collector.discover_united_states(self.source, self.start, self.end)
        self.assertEqual(home, self.source["url"])
        self.assertEqual({x["title"] for x in items}, {"security-statement", "fire-prevention"})
        self.assertEqual({x["published_date"] for x in items}, {"2026-10-09", "2026-10-05"})
        self.assertEqual(mocked.call_count, 3)  # two archive pages and a full article

    def test_rejects_links_outside_official_article_section(self):
        page = card(9, "valid").replace("https://www.whitehouse.gov/briefings-statements/", "https://example.org/")
        with patch.object(collector, "fetch", return_value=(self.source["url"], page.encode())):
            with self.assertRaisesRegex(RuntimeError, "invalid article URL"):
                collector.discover_united_states(self.source, self.start, self.end)

    def test_every_official_news_category_is_acquired_once(self):
        categories=('briefings-statements','releases','fact-sheets','presidential-actions','remarks','research')
        cards=''.join(card(9,category).replace('/briefings-statements/',f'/{category}/') for category in categories)
        cards+=card(9,'releases').replace('/briefings-statements/','/releases/')
        with patch.object(collector,'fetch',return_value=(self.source['url'],cards.encode())),patch.object(collector,'article_text',return_value='Complete original body'):
            items,_=collector.discover_united_states(self.source,self.start,self.end)
        self.assertEqual(len(items),6)
        self.assertEqual({item['url'].split('/')[3] for item in items},set(categories))
        self.assertEqual(self.source['url'],'https://www.whitehouse.gov/news/')


if __name__ == "__main__":
    unittest.main()
