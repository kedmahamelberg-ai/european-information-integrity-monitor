import datetime as dt
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import collect_government_news as collector


class AustriaArchiveTests(unittest.TestCase):
    country={'name':'Austria', 'iso2':'AT', 'url':
        'https://www.bundeskanzleramt.gv.at/bundeskanzleramt/nachrichten-der-bundesregierung/2026.html'}
    start=dt.datetime.fromisoformat('2026-09-30T22:00:00+00:00')
    end=dt.datetime.fromisoformat('2026-11-26T18:00:00+00:00')

    def card(self, month, day, slug):
        return f'<a href="/bundeskanzleramt/nachrichten-der-bundesregierung/2026/{month:02}/{slug}.html"><small class="card-date">{day}. November 2026</small><h2>Official {slug}</h2></a>'

    def test_monthly_pagination_includes_october_and_november_without_stale_year_page(self):
        requests=[]
        def fetch(url):
            requests.append(url)
            if url.endswith('/2026/10.html'):
                return url,self.card(10,1,'october').encode()
            if url.endswith('/2026/11.html'):
                return url,(self.card(11,26,'first')+'<a href="?currentPage=1">Next</a>').encode()
            if url.endswith('/2026/11.html?currentPage=1'):
                return url,self.card(11,2,'second').encode()
            return url,b'<main>Full original source</main>'
        with patch.object(collector,'fetch',side_effect=fetch), patch.object(collector,'publication_date',return_value=self.end):
            rows,_=collector.discover_austria(self.country,self.start,self.end)
        self.assertEqual(len(rows),3)
        self.assertEqual({r['published_date'] for r in rows},{'2026-10-01','2026-11-26','2026-11-02'})
        self.assertNotIn(self.country['url'],requests)

    def test_stale_month_or_unparseable_page_cannot_pass_as_empty_archive(self):
        for body in (self.card(6,29,'stale'),'<html>Temporary error</html>'):
            with self.subTest(body=body),patch.object(collector,'fetch',return_value=(self.country['url'],body.encode())):
                with self.assertRaises(RuntimeError):
                    collector.discover_austria(self.country,self.start,self.end)
