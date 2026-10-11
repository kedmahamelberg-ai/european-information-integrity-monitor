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
    def test_selection_uses_video_clusters_and_their_comments(self):
        comments = {
            f"v{i}": ([f"v{i}-c1", f"v{i}-c2"] if i < 20 else [])
            for i in range(178)
        }
        population = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "batch": "2026-W41",
            "video_ids": [f"v{i}" for i in range(178)],
            "video_comments": comments,
        }
        result = review_selection.selection(population, "2026-W41")
        self.assertEqual(result["video_population"], 178)
        self.assertEqual(len(result["selected_video_ids"]), 6)
        self.assertEqual(result["comment_population"], 40)
        self.assertTrue(result["selected_comment_ids"])
        self.assertEqual(
            result["selected_comment_ids"],
            sorted(
                cid
                for vid in result["selected_video_ids"]
                for cid in comments[vid]
            ),
        )

    def test_batch_mismatch_fails_closed(self):
        population = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "batch": "2026-W40",
            "video_ids": [],
            "video_comments": {},
        }
        with self.assertRaises(ValueError):
            review_selection.selection(population, "2026-W41")
