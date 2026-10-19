"""Exercise source parsing and URL deduplication without APIs or classification."""
import ast
import datetime as dt
import hashlib
import html
from pathlib import Path
import re
import unittest
import urllib.parse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "scripts/collect_government_news.py").read_text())
names = {"canonical_source_url", "canonical_government_items", "discover_iceland"}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
         or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SOURCE_URL_ALIASES" for t in n.targets)]
scope = dict(dt=dt, hashlib=hashlib, html=html, re=re, urllib=urllib, REYKJAVIK=ZoneInfo("Atlantic/Reykjavik"))
exec(compile(ast.Module(body=nodes, type_ignores=[]), "<collector-source-functions>", "exec"), scope)


class GovernmentRecoveryTests(unittest.TestCase):
    def test_renamed_pending_item_reuses_existing_classification(self):
        old, new = next(iter(scope["SOURCE_URL_ALIASES"].items()))
        records = [{"url":old,"classification_status":"pending_classification"},
                   {"url":new,"classification_status":"provisional","topics":["cyber"],"ticker_message":"Saved classification"}]
        for order in (records, records[::-1]):
            result = list(scope["canonical_government_items"](order).values())
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["topics"], ["cyber"])
            self.assertEqual(result[0]["ticker_message"], "Saved classification")
            self.assertEqual(result[0]["source_aliases"], [old])

    def test_human_review_wins_over_model_alias(self):
        old, new = next(iter(scope["SOURCE_URL_ALIASES"].items()))
        result = list(scope["canonical_government_items"]([
            {"url":old,"classification_status":"human_reviewed","related":False},
            {"url":new,"classification_status":"provisional","related":True}]).values())
        self.assertEqual(len(result),1)
        self.assertFalse(result[0]["related"])

    def test_iceland_uuid_trailing_slash_is_same_item(self):
        url="https://www.stjornarradid.is/efst-a-baugi/frettir/stok-frett/345973f7-4e13-4982-b704-d9996149d06e"
        result=scope["canonical_government_items"]([{"url":url},{"url":url+"/"}])
        self.assertEqual(len(result),1)

    def test_iceland_uuid_uses_card_publication_date(self):
        base="https://www.stjornarradid.is/efst-a-baugi/frettir/"
        def card(slug,date):
            return f'<article class="search-result-card"><a href="{base}stok-frett/{slug}" class="search-result-card-link"><h3 class="search-result-card-title title">Official statement</h3><span class="search-result-card-date">{date}</span></a></article>'
        body=card("345973f7-4e13-4982-b704-d9996149d06e/","19. október 2026")+card("2026-10-17-older","17. október 2026")
        scope["fetch"]=lambda url:(url,body.encode())
        entries,_=scope["discover_iceland"]({"url":base,"iso2":"IS","name":"Iceland"},dt.datetime(2026,10,18,tzinfo=dt.timezone.utc),dt.datetime(2026,10,19,13,tzinfo=dt.timezone.utc))
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]["published_date"],"2026-10-19")
        self.assertEqual(entries[0]["publication_precision"],"day")

    def test_unrelated_iceland_path_is_rejected(self):
        body='<article class="search-result-card"><a href="https://example.org/news" class="search-result-card-link"><h3 class="search-result-card-title title">Other</h3><span class="search-result-card-date">19. október 2026</span></a></article>'
        scope["fetch"]=lambda url:(url,body.encode())
        with self.assertRaisesRegex(RuntimeError,"Unexpected Icelandic"):
            scope["discover_iceland"]({"url":"https://www.stjornarradid.is/efst-a-baugi/frettir/","iso2":"IS","name":"Iceland"},dt.datetime(2026,10,18,tzinfo=dt.timezone.utc),dt.datetime(2026,10,19,tzinfo=dt.timezone.utc))
