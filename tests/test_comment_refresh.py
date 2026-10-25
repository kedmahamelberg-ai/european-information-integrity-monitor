import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from eiim.hybrid import collect_week
from eiim.pipeline import Pipeline
from eiim.storage import MemoryStore, record
from test_pipeline import FixtureLocal, FixtureClassifier, FixtureYouTube


class CommentMinimumTests(unittest.TestCase):
    def test_recovered_sources_get_comments_after_stale_complete_stage(self):
        store = MemoryStore()
        pipe = Pipeline(store, local=FixtureLocal(), classifier=FixtureClassifier())
        store.batch(pipe.window, "fixture")
        samples = [
            {"video_id": vid, "selected_for_sample": True}
            for vid in ("first", "recovered", "no-comments")
        ]
        store.write(pipe.id, [
            row for sample in samples for row in (
                record("sampled_videos", pipe.id, pipe.id + ":" + sample["video_id"],
                       sample, sample["video_id"]),
                record("candidate_videos", pipe.id, pipe.id + ":" + sample["video_id"],
                       {"video_id": sample["video_id"], "comment_count":
                        0 if sample["video_id"] == "no-comments" else 20}, sample["video_id"]),
            )
        ], "discovery_complete")
        store.write(pipe.id, [], "sampling_complete")

        class CountingYouTube(FixtureYouTube):
            def __init__(self):
                self.calls = []

            def comments(self, vid):
                self.calls.append(vid)
                return super().comments(vid)

        youtube = CountingYouTube()
        eligible = {}
        with (
            patch("eiim.pipeline.Pipeline", return_value=pipe),
            patch.object(pipe, "prepare_english_access"),
            patch("eiim.services.YouTube", return_value=youtube),
            patch("eiim.services.LocalModel", return_value=FixtureLocal()),
            patch("eiim.hybrid.Classifier", return_value=FixtureClassifier()),
            patch("eiim.hybrid.retrieve_retained_captions"),
            patch("eiim.hybrid.retained_inputs", side_effect=lambda *_: (eligible, [])),
            patch("eiim.hybrid.reclassify", return_value={}),
        ):
            collect_week(store)
            self.assertNotIn("comments_complete", store.read("weekly_batches", pipe.id)[0]["completed_stages"])
            eligible["first"] = {}
            collect_week(store)
            self.assertEqual(youtube.calls, ["first"])
            self.assertNotIn("comments_complete", store.read("weekly_batches", pipe.id)[0]["completed_stages"])
            # Simulate the premature stage written by previous collector versions.
            store.write(pipe.id, [], "comments_complete")
            eligible.update({"recovered": {}, "no-comments": {}})
            collect_week(store)
            self.assertEqual(youtube.calls, ["first", "recovered"])
            self.assertEqual(len(store.read("comments", pipe.id)), 40)
            self.assertEqual(len({r["id"] for r in store.read("comments", pipe.id)}), 40)
            self.assertEqual(len([r for r in store.read("pipeline_runs", pipe.id)
                                  if "comment_video_id" in r["payload"]]), 3)
            before = copy.deepcopy(store.tables)
            collect_week(store)
            self.assertEqual(youtube.calls, ["first", "recovered"])
            self.assertEqual(store.tables, before)

    def test_targeted_refresh_never_fetches_other_eligible_videos(self):
        store = MemoryStore()
        pipe = Pipeline(
            store,
            datetime.fromisoformat("2026-10-04T05:00:00Z"),
            local=FixtureLocal(),
            classifier=FixtureClassifier(),
        )
        store.batch(pipe.window, "fixture")
        rows = []
        for vid in ("target", "other"):
            rows.extend((
                record("candidate_videos", pipe.id, pipe.id + ":" + vid,
                       {"video_id": vid, "comment_count": 2, "original_audio_language": "en"}, vid),
                record("sampled_videos", pipe.id, pipe.id + ":" + vid,
                       {"video_id": vid, "selected_for_sample": True}, vid),
            ))
        store.write(pipe.id, rows)

        class CountingYouTube(FixtureYouTube):
            def __init__(self):
                self.calls = []

            def comments(self, vid):
                self.calls.append(vid)
                return super().comments(vid)

        pipe.yt = CountingYouTube()
        pipe.cfg["minimum_available_comments"] = 2
        pipe.comments(refresh_policy=True, mark_complete=False,
                      only_video_ids={"target"})
        self.assertEqual(pipe.yt.calls, ["target"])
        self.assertEqual({r["video_id"] for r in store.read("comments")}, {"target"})

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
