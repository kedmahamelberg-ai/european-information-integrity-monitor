"""The official San Marino feed is paginated and not sorted by date."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location(
    "collect_government_news", Path(__file__).resolve().parents[1] / "scripts/collect_government_news.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def row(number, day):
    return {"newsType":"Comunicati", "@id":f"00000000-0000-0000-0000-{number:012d}",
            "dataIn":f"{day}T12:00:00+01:00", "title":"Official release",
            "testo":"A full official communication about government affairs and public policy."}


class SanMarinoCollectorTests(unittest.TestCase):
    def test_reads_all_pages_including_recent_items_on_later_page(self):
        pages=[{"total":1001,"offset":0,"limit":1000,"results":[row(i,"2020-01-01") for i in range(1000)]},
               {"total":1001,"offset":1000,"limit":1000,"results":[row(1000,"2026-11-12")]}]
        country={"iso2":"SM","name":"San Marino","url":"https://www.gov.sm/pub1/EsteriSM/Ufficio-Stampa/News-e-Comunicati.html"}
        start=dt.datetime(2026,11,9,tzinfo=collector.ROME)
        end=dt.datetime(2026,11,15,tzinfo=collector.ROME)
        with patch.object(collector,"fetch",side_effect=[("url",json.dumps(p).encode()) for p in pages]) as fetch:
            items,_=collector.discover_san_marino(country,start,end)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["published_date"],"2026-11-12")
        self.assertIn("offset=1000",fetch.call_args_list[1].args[0])


if __name__ == "__main__": unittest.main()
