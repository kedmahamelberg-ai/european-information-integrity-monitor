"""The two additional benchmarks must traverse dated official sources without duplicates."""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_government_news as collector


def atom(entries):
    rows = "".join(f'''<entry><title>{title}</title><updated>{date}</updated>
        <link href="{url}"/></entry>''' for title, date, url in entries)
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{rows}</feed>'.encode()


class BenchmarkCollectorTest(unittest.TestCase):
    def test_explicit_ai_titles_are_reviewed_first_without_assigning_labels(self):
        neutral={"id":"neutral", "title":"Les ministres ont parlé; j'ai répondu"}
        french={"id":"french", "title":"L'intelligence artificielle et la sécurité"}
        english={"id":"english", "title":"Canada invests in AI safety research"}
        general={"id":"general", "title":"Superintelligence governance proposal"}
        screened={"id":"f674ed27a764f88771ee", "title":"Security training technology"}
        self.assertEqual(collector.classification_order(neutral)[0],2)
        self.assertEqual([collector.classification_order(x)[0] for x in (french,english,general)],[0,0,0])
        self.assertEqual(collector.classification_order(screened)[0],1)
        self.assertTrue(all("topics" not in x for x in (neutral,french,english,general,screened)))

    def test_canada_keeps_french_only_release_but_deduplicates_translation(self):
        source=next(x for x in collector.SOURCES if x["iso2"]=="CA")
        en='https://www.canada.ca/en/agency/news/2026/10/one.html'
        fr='https://www.canada.ca/fr/agence/nouvelles/2026/10/un.html'
        fr_only='https://www.canada.ca/fr/agence/nouvelles/2026/10/deux.html'
        older='2026-09-30T12:00:00-04:00'
        shared='2026-10-03T12:00:00-04:00'
        unique='2026-10-02T12:00:00-04:00'
        def fetched(url,**_):
            # The live API returns an empty feed for its date-filter query.
            if 'publishedDate%3E=' in url or 'publishedDate=' in url:
                return url,b'<feed xmlns="http://www.w3.org/2005/Atom"><updated>Invalid date</updated></feed>'
            if '/en/' in url:
                return url,atom([('English release',shared,en),('Older release',older,en)])
            return url,atom([('Communiqué traduit',shared,fr),('Communiqué français',unique,fr_only),('Ancien',older,fr)])
        def issued(url): return dt.date(2026,10,2) if url==fr_only else dt.date(2026,10,3)
        with patch.object(collector,'fetch',side_effect=fetched),patch.object(collector,'canada_release_date',side_effect=issued):
            items,_=collector.discover_canada(source,dt.datetime(2026,10,1,tzinfo=dt.timezone.utc),dt.datetime(2026,10,5,tzinfo=dt.timezone.utc))
        self.assertEqual({x['url'] for x in items},{en,fr_only})
        self.assertTrue(all(x['publication_precision']=='day' for x in items))
        self.assertEqual(collector.COUNTRY_ISO3['CA'],'CAN')

    def test_canada_excludes_a_feed_update_for_a_prelaunch_release(self):
        source=next(x for x in collector.SOURCES if x['iso2']=='CA')
        old='https://www.canada.ca/fr/agence/nouvelles/2026/09/ancien.html'
        # The English feed must still contain a valid entry; only the French
        # item has an original date before the requested collection window.
        en='https://www.canada.ca/en/agency/news/2026/10/new.html'
        def feed(url,**_):
            return url,atom([('New release','2026-10-30T12:00:00-04:00',en)] if '/en/' in url else [('Ancien communiqué','2026-10-30T09:48:12-04:00',old)])
        with patch.object(collector,'fetch',side_effect=feed),patch.object(collector,'canada_release_date',side_effect=lambda u:dt.date(2026,9,4) if u==old else dt.date(2026,10,30)):
            items,_=collector.discover_canada(source,dt.datetime(2026,10,1,tzinfo=dt.timezone.utc),dt.datetime(2026,10,31,tzinfo=dt.timezone.utc))
        self.assertEqual([x['url'] for x in items],[en])

    def test_china_accepts_official_policy_link_in_news_archive_and_stops_at_start(self):
        source=next(x for x in collector.SOURCES if x['iso2']=='CN')
        policy='https://english.www.gov.cn/policies/latestreleases/202610/05/content_WS6abc1234.html'
        older='https://english.www.gov.cn/news/202609/30/content_WS6abc5678.html'
        page=f'''<div class="TopNews_List_Div"><ul>
          <li><h3><a href="{policy}">State Council policy</a></h3><h4>2026/10/05</h4></li>
          <li><h3><a href="{older}">Older story</a></h3><h4>2026/09/30</h4></li>
          </ul></div>'''.encode()
        with patch.object(collector,'fetch',return_value=(source['url'],page)) as fetched,patch.object(collector,'article_text',return_value='Full official article'):
            items,_=collector.discover_china(source,dt.datetime(2026,10,1,tzinfo=dt.timezone.utc),dt.datetime(2026,10,6,tzinfo=dt.timezone.utc))
        self.assertEqual([x['url'] for x in items],[policy])
        self.assertEqual(fetched.call_count,1)
        self.assertEqual(collector.COUNTRY_ISO3['CN'],'CHN')


if __name__=='__main__': unittest.main()
