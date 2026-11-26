"""Check the DOI archive, RSS fallback, and per-article retrieval."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
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
ENGLISH_URL = "https://departmentofinformation.gov.mt/press-release/2026/pr261925en"


class MaltaCollectorTests(unittest.TestCase):
    def setUp(self):
        self.country = {"iso2": "MT", "name": "Malta", "url": collector.MALTA_ARCHIVE}
        self.start = dt.datetime(2026, 11, 9, tzinfo=collector.MALTA)
        self.end = dt.datetime(2026, 11, 15, 23, tzinfo=collector.MALTA)

    def test_paginates_prefers_english_and_uses_rss_text(self):
        first = ('<html>' + card("PR261925", "Maltese title") +
                 '<a href="/en/search/press-releases?p=2">2</a></html>')
        second = '<html>' + card("PR261925EN", "English title") + card("PR261926", "Other title") + '</html>'
        feed = {ENGLISH_URL: "Official government communication with enough article text for a full classification."}
        with patch.object(collector, "fetch_malta_html", side_effect=[first, second]) as fetch, \
             patch.object(collector, "malta_rss_text", return_value=feed):
            items, home = collector.discover_malta(self.country, self.start, self.end)
        self.assertEqual(len(items), 2)
        self.assertEqual(home, self.country["url"])
        self.assertEqual(items[0]["title"], "English title")
        self.assertEqual(items[0]["published_date"], "2026-11-14")
        self.assertEqual(items[0]["url"], ENGLISH_URL)
        self.assertIn("Official government communication", items[0]["text"])
        self.assertEqual(fetch.call_count, 2)  # No article fetch can abort discovery.

    def test_english_translation_without_en_suffix_is_one_release_in_either_order(self):
        maltese=card('PR261927','STQARRIJA MILL-MINISTERU Climate negotiations', '15/11/2026')
        english=card('PR261927','PRESS RELEASE BY THE MINISTRY Climate negotiations', '15/11/2026').replace('pr261927"','pr261927-0"')
        for rows in ([maltese,english],[english,maltese]):
            with patch.object(collector,'fetch_malta_html',return_value=''.join(rows)), \
                 patch.object(collector,'malta_rss_text',return_value={}):
                items,_=collector.discover_malta(self.country,self.start,self.end)
            self.assertEqual(len(items),1)
            self.assertTrue(items[0]['url'].endswith('/pr261927-0'))
            self.assertEqual(items[0]['source_aliases'],['https://departmentofinformation.gov.mt/press-release/2026/pr261927'])

    def test_conflicting_same_language_release_still_requires_source_review(self):
        a=card('PR261927','PRESS RELEASE BY THE MINISTRY One', '15/11/2026')
        b=card('PR261927','PRESS RELEASE BY THE MINISTRY Another', '15/11/2026').replace('pr261927"','pr261927-0"')
        with patch.object(collector,'fetch_malta_html',return_value=a+b), \
             patch.object(collector,'article_text',side_effect=['Full original one.','A different original.']):
            with self.assertRaisesRegex(RuntimeError,'identity needs review'):
                collector.discover_malta(self.country,self.start,self.end)

    def test_republished_same_language_copy_requires_identical_complete_bodies(self):
        a=card('PR261861','STQARRIJA Original', '15/11/2026')
        b=card('PR261861','STQARRIJA Original', '15/11/2026').replace('pr261861"','pr261861-1"')
        with patch.object(collector,'fetch_malta_html',return_value=a+b), \
             patch.object(collector,'article_text',return_value='The same complete official original.') as read, \
             patch.object(collector,'malta_rss_text',return_value={}):
            items,_=collector.discover_malta(self.country,self.start,self.end)
        self.assertEqual(read.call_count,2)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['source_aliases'],['https://departmentofinformation.gov.mt/press-release/2026/pr261861-1'])

    def test_republished_typographic_quotes_preserve_all_words_and_numbers(self):
        a=card('PR261861','STQARRIJA Original', '15/11/2026')
        b=a.replace('pr261861"','pr261861-1"')
        first='The minister said: “The workers’ 2027–2031 strategy.”'
        same='The minister said: "The workers\' 2027–2031 strategy."'
        for second,accepted in [(same,True),(same.replace('2031','2032'),False),
                                (same.replace('workers','employers'),False)]:
            with self.subTest(second=second),patch.object(collector,'fetch_malta_html',return_value=a+b), \
                 patch.object(collector,'article_text',side_effect=[first,second]), \
                 patch.object(collector,'malta_rss_text',return_value={}):
                if accepted:
                    self.assertEqual(len(collector.discover_malta(self.country,self.start,self.end)[0]),1)
                else:
                    with self.assertRaisesRegex(RuntimeError,'identity needs review'):
                        collector.discover_malta(self.country,self.start,self.end)

    def test_only_reviewed_duplicate_final_full_stop_is_normalized(self):
        self.assertEqual(collector.malta_identity_text('The source sentence. .'),'The source sentence.')
        self.assertEqual(collector.malta_identity_text('An omission . . .'),'An omission . . .')
        self.assertNotEqual(collector.malta_identity_text('Total 10.5.'),collector.malta_identity_text('Total 105.'))

    def test_all_conflicting_originals_are_saved_for_one_source_review(self):
        rows=''.join(card(n,'Same printed release')+card(n,'Same printed release').replace(n.lower()+'"',n.lower()+'-1"') for n in ['PR261858','PR261859'])
        with tempfile.TemporaryDirectory() as folder,patch.object(collector,'ROOT',Path(folder)), \
             patch.object(collector,'fetch_malta_html',return_value=rows), \
             patch.object(collector,'article_text',side_effect=['First full original.','Changed full original.']*2) as read:
            with self.assertRaisesRegex(RuntimeError,'identity needs review'):
                collector.discover_malta(self.country,self.start,self.end)
            evidence=json.loads((Path(folder)/'data/government_source_identity_review.json').read_text())
        self.assertEqual(read.call_count,4)
        self.assertEqual({row['release_id'] for row in evidence},{'pr261858','pr261859'})

    def test_fetches_article_body_when_rss_does_not_cover_it(self):
        item = {"country_code": "MT", "url": ENGLISH_URL, "text": ""}
        with patch.object(collector, "fetch_malta_html", return_value=ARTICLE):
            body = collector.article_text(item)
        self.assertIn("Official government communication", body)
        self.assertEqual(item["text"], body)

    def test_rejects_incomplete_article(self):
        item = {"country_code": "MT", "url": ENGLISH_URL, "text": ""}
        with patch.object(collector, "fetch_malta_html", return_value="<html>No article</html>"):
            with self.assertRaisesRegex(RuntimeError, "usable article body"):
                collector.article_text(item)

    def test_reads_full_text_from_official_rss(self):
        rss = ('<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>'
               f'<link>{ENGLISH_URL}</link><content:encoded><![CDATA[<p>Official government communication with enough article text for a full classification.</p>]]></content:encoded>'
               '</item></channel></rss>')
        with patch.object(collector, "fetch_malta_html", return_value=rss):
            result = collector.malta_rss_text()
        self.assertIn(ENGLISH_URL, result)
        self.assertIn("Official government communication", result[ENGLISH_URL])

    def test_rejects_nonofficial_url(self):
        with self.assertRaisesRegex(RuntimeError, "left the official"):
            collector.fetch_malta_html("https://example.com/other")


if __name__ == "__main__": unittest.main()
