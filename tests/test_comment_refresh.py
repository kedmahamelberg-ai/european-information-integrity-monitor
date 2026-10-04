import copy
import unittest
from datetime import datetime
from eiim.pipeline import Pipeline
from eiim.storage import MemoryStore, record
from test_pipeline import FixtureLocal, FixtureClassifier, FixtureYouTube


class CommentMinimumTests(unittest.TestCase):
    def test_two_comment_boundary_and_revisit_old_exclusions_without_rewriting(self):
        store = MemoryStore()
        pipe = Pipeline(
            store,
            datetime.fromisoformat("2026-10-04T05:00:00Z"),
            local=FixtureLocal(),
            classifier=FixtureClassifier(),
        )
        store.batch(pipe.window, "fixture")
        counts = {"zero": 0, "one": 1, "two": 2, "nineteen": 19, "inaccessible": 20}
        rows = []
        for vid, count in counts.items():
            rows += [
                record(
                    "candidate_videos",
                    pipe.id,
                    pipe.id + ":" + vid,
                    {
                        "video_id": vid,
                        "comment_count": count,
                        "original_audio_language": "en",
                    },
                    vid,
                ),
                record(
                    "sampled_videos",
                    pipe.id,
                    pipe.id + ":" + vid,
                    {"video_id": vid, "selected_for_sample": True},
                    vid,
                ),
            ]
        store.write(pipe.id, rows)

        class YouTube(FixtureYouTube):
            def __init__(self):
                self.calls = []

            def comments(self, vid):
                self.calls.append(vid)
                pool, status = super().comments(vid)
                size = 1 if vid == "inaccessible" else counts[vid]
                return pool[:size], status

        pipe.yt = YouTube()
        pipe.cfg["minimum_available_comments"] = 20
        pipe.comments()
        self.assertEqual(pipe.yt.calls, ["inaccessible"])
        self.assertEqual(store.read("comments"), [])
        original = copy.deepcopy(store.read("pipeline_runs"))
        pipe.cfg["minimum_available_comments"] = 2
        pipe.comments(refresh_policy=True, mark_complete=False)
        self.assertEqual(len(store.read("comments")), 21)
        self.assertEqual(
            {r["video_id"] for r in store.read("comments")}, {"two", "nineteen"}
        )
        self.assertEqual(
            pipe.yt.calls, ["inaccessible", "two", "nineteen", "inaccessible"]
        )
        saved = {r["id"]: r for r in store.read("pipeline_runs")}
        self.assertTrue(all(saved[r["id"]] == r for r in original))
        before = copy.deepcopy(store.tables)
        pipe.comments(refresh_policy=True, mark_complete=False)
        self.assertEqual(store.tables, before)
        self.assertEqual(len(pipe.yt.calls), 4)
