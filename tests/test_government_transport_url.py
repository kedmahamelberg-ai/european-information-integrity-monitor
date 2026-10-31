"""Official links remain human-readable while HTTP requests use ASCII URLs."""
import ast
from pathlib import Path
import ssl
import subprocess
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request


ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT/"scripts/collect_government_news.py").read_text())
names={"transport_url","_fetch_once","fetch_ipv4"}
nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
scope={"urllib":urllib,"ssl":ssl,"subprocess":subprocess,"UA":"test-agent"}
exec(compile(ast.Module(body=nodes,type_ignores=[]),"<government-transport>","exec"),scope)


class GovernmentTransportURLTests(unittest.TestCase):
    def test_unicode_path_and_query_are_encoded_once(self):
        source="https://www.gouv.mc/actualites/communiqué-ᵉ?topic=é&lang=fr#section"
        request=scope["transport_url"](source)
        self.assertEqual(request,"https://www.gouv.mc/actualites/communiqu%C3%A9-%E1%B5%89?topic=%C3%A9&lang=fr")
        self.assertEqual(scope["transport_url"](request),request)
        self.assertTrue(request.isascii())

    def test_unicode_hostname_uses_idna(self):
        self.assertEqual(scope["transport_url"]("https://münchen.example/étude"),
                         "https://xn--mnchen-3ya.example/%C3%A9tude")

    def test_fetch_uses_encoded_request_but_preserves_source_url(self):
        source="https://www.gouv.mc/actualites/communiqué-ᵉ"
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return source
            def read(self,limit):return b"official article"
        def urlopen(req,timeout):
            self.assertTrue(req.selector.isascii())
            self.assertIn("%E1%B5%89",req.selector)
            return Response()
        with patch.object(urllib.request,"urlopen",side_effect=urlopen):
            final,body=scope["_fetch_once"](source)
        self.assertEqual((final,body),(source,b"official article"))

    def test_bad_url_is_rejected_before_request(self):
        with self.assertRaises(ValueError):scope["transport_url"]("/actualites/relative")


if __name__=="__main__":unittest.main()
