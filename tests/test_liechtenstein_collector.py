import datetime as dt
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import collect_government_news as collector


def card(day,ident):
    return f'<div class="shortmsg item"><div class="shortmsg__date">{day}. Oktober 2026</div><div class="shortmsg__text">Government announcement {ident}</div><a class="shortmsg__more" href="/medienportal-medium/16182/{ident}/0/medienmitteilung">Details</a></li>'


class LiechtensteinCollectorTests(unittest.TestCase):
    def setUp(self):
        self.source=next(x for x in collector.SOURCES if x['iso2']=='LI')
        self.start=dt.datetime(2026,10,1,tzinfo=collector.VADUZ)

    def test_date_windows_acquire_older_records_and_explicit_empty_results(self):
        pages=[card(2,1).replace('/1/0/','/1/1/'),'<div>Keine Eintr&#xE4;ge gefunden</div>',card(16,2)]
        with patch.object(collector,'fetch',side_effect=lambda url,**_:(url,pages.pop(0).encode())) as fetched:
            items,_=collector.discover_liechtenstein(self.source,self.start,self.start+dt.timedelta(days=20))
        self.assertEqual([x['published_date'] for x in items],['2026-10-02','2026-10-16'])
        self.assertEqual(fetched.call_count,3)
        self.assertTrue(all('years=' in call.args[0] for call in fetched.call_args_list))

    def test_more_results_split_the_window_before_accepting_it(self):
        pages=['<a class="show-more-links">More</a>',card(2,1),card(5,2)]
        with patch.object(collector,'fetch',side_effect=lambda url,**_:(url,pages.pop(0).encode())):
            items,_=collector.discover_liechtenstein(self.source,self.start,self.start+dt.timedelta(days=6))
        self.assertEqual(len(items),2)

    def test_ignored_filter_or_truncated_single_day_cannot_pass(self):
        for page,error in [(card(20,1),'ignored'),('<a class="show-more-links">More</a>','single-day')]:
            with self.subTest(error=error),patch.object(collector,'fetch',return_value=('source',page.encode())):
                with self.assertRaisesRegex(RuntimeError,error):
                    collector.discover_liechtenstein(self.source,self.start,self.start)


if __name__=='__main__':unittest.main()
