import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from search_pages import add_page_view_script


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append(dict(attrs).get("src", "").split("?")[0].lstrip("/"))


class TrafficCoverage(unittest.TestCase):
    def test_all_public_landings_get_one_ordered_set_of_measurement_scripts(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            assets = ["analytics.js", "visitor-count.js", "page-views.js"]
            for asset in assets:
                (root / asset).write_text("// test")
            pages = ["index.html", "contact.html", "privacy.html", "about.html", "research.html",
                     "field-wire/index.html", "field-wire/2026-11-26/index.html", "findings/test/index.html"]
            for page in pages:
                p = root / page
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('<head><script defer src="/analytics.js?v=old"></script></head>')
            for _ in range(2):
                add_page_view_script(root, [{"path": "/findings/test/"}], ["2026-11-26"])
            for page in pages:
                parser = Scripts()
                parser.feed((root / page).read_text())
                self.assertEqual(parser.scripts, assets, page)
