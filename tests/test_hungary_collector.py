"""Hidden publication dates must not crash or fabricate archive coverage."""
import datetime as dt
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect_government_news import discover_hungary

class HungaryCollectorTests(unittest.TestCase):
    def test_hidden_date_card_does_not_discard_dated_neighbours(self):
        rows = [dict(name='Undated', slug='undated', date=None, ministry=None, isHiddenDate=True),
                dict(name='Dated', slug='dated', date='2026-11-26', ministry=None)]
        payload = json.dumps(dict(data=rows, meta=dict(pagination=dict(page=1, itemsTotal=2)))).encode()
        with patch('collect_government_news.fetch', return_value=(None, payload)):
            items, _ = discover_hungary(dict(name='Hungary', url='https://kormany.hu/hirek'),
                dt.datetime(2026,11,25,tzinfo=dt.timezone.utc), dt.datetime(2026,11,27,tzinfo=dt.timezone.utc))
        self.assertEqual([x['title'] for x in items], ['Dated'])
        self.assertEqual(items[0]['published_date'], '2026-11-26')

    def test_unexpected_missing_date_still_fails(self):
        payload = json.dumps(dict(data=[dict(name='Broken', slug='broken', date=None)],
                                  meta=dict(pagination=dict(page=1, itemsTotal=1)))).encode()
        with patch('collect_government_news.fetch', return_value=(None,payload)):
            with self.assertRaisesRegex(RuntimeError, 'no publication date'):
                discover_hungary(dict(name='Hungary', url='https://kormany.hu/hirek'),
                    dt.datetime(2026,11,25,tzinfo=dt.timezone.utc), dt.datetime(2026,11,27,tzinfo=dt.timezone.utc))
