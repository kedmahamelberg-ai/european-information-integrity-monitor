from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "review_selection",
    Path(__file__).resolve().parents[1] / "scripts/review_selection.py",
)
review_selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_selection)


class ReviewSelectionTests(unittest.TestCase):
    def test_selection_uses_full_video_and_comment_populations(self):
        population = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "batch": "2026-W41",
            "video_ids": [f"v{i}" for i in range(178)],
            "comment_ids": [f"c{i}" for i in range(201)],
        }
        result = review_selection.selection(population, "2026-W41")
        self.assertEqual(result["video_population"], 178)
        self.assertEqual(len(result["selected_video_ids"]), 6)
        self.assertEqual(result["comment_population"], 201)
        self.assertEqual(len(result["selected_comment_ids"]), 7)

    def test_batch_mismatch_fails_closed(self):
        population = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "batch": "2026-W40",
            "video_ids": [],
            "comment_ids": [],
        }
        with self.assertRaises(ValueError):
            review_selection.selection(population, "2026-W41")
