from datetime import date
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest
from importlib.util import find_spec

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from field_wire import render


class FieldWireEditions(unittest.TestCase):
    @unittest.skipUnless(find_spec("PIL"), "edition image tests require the publish extra")
    def test_rotation_and_intraday_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive"

            def build(index, day, key, finding):
                dest = root / str(index)
                dest.mkdir()
                row = dict(id=key, related=True, classification_status="human_reviewed", country_code="NL",
                           country="Netherlands", published_date=f"2026-11-{day}", ticker_message=finding)
                render(dest, {}, {"items": [row]}, archive, date(2026, 11, day))
                return dest / "field-wire"

            first = build(1, 21, "abc", "Original finding.")
            second = build(2, 21, "abc", "Corrected finding.")
            old = second / "2026-11-21"
            html = (old / "index.html").read_text()
            self.assertIn('id="gov-abc"', html)
            self.assertIn("Original finding.", html)
            self.assertIn("Corrected finding.", html)
            self.assertIn('href="/?record=abc#government"', html)
            self.assertRegex((second / "index.html").read_text(), r'id="gov-abc-[a-f0-9]{12}"')
            third = build(3, 22, "def", "Next edition.")
            for asset in ("index.html", "preview.png"):
                self.assertEqual((third / old.name / asset).read_bytes(), (old / asset).read_bytes())
            self.assertEqual(struct.unpack(">II", (first / old.name / "preview.png").read_bytes()[16:24]), (1280, 720))
            self.assertEqual(set(json.loads((third / "items.json").read_text())), {"gov-abc", "gov-def"})
            live = (third / "index.html").read_text()
            self.assertIn('href="/field-wire/2026-11-21/"', live)
            self.assertNotIn("Original finding.", live)
            self.assertIn('data-edition="/field-wire/2026-11-22/"', live)
            self.assertNotIn("adsbygoogle", html)

    def test_empty_export_creates_no_edition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(render(root, {}, {}, root / "archive"), [])
            self.assertNotIn("preview.png", (root / "field-wire/index.html").read_text())
