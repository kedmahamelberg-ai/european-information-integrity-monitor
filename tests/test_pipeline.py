import unittest, copy, tempfile, json
from pathlib import Path
from datetime import datetime
from eiim.pipeline import Pipeline
from eiim.storage import MemoryStore
from eiim.core import validate_classification, config
from eiim.cli import export_public
from test_core import label


class FixtureYouTube:
    def discover(self, window):
        return [f"fixture-{i}" for i in range(9)]

    def resources(self, kind, ids, part):
        if kind == "videos":
            return [
                {
                    "id": id,
                    "snippet": {
                        "title": "Netherlands policy discussion " + id,
                        "description": "Public affairs policy fixture",
                        "channelId": "channel-" + id,
                        "channelTitle": "Synthetic channel",
                        "publishedAt": "2026-09-30T12:00:00Z",
                        "categoryId": "25",
                        "defaultAudioLanguage": "en",
                    },
                    "statistics": {"commentCount": "20"},
                }
                for id in ids
            ]
        return [
            {
                "id": id,
                "snippet": {
                    "publishedAt": "2010-01-01T00:00:00Z",
                    "description": "https://example.org",
                },
                "statistics": {
                    "subscriberCount": str(100 * (i + 1) ** 3),
                    "videoCount": str(100 * (i + 1)),
                },
            }
            for i, id in enumerate(ids)
        ]

    def comments(self, vid):
        return (
            [
                {
                    "comment_id": vid + "-" + str(i),
                    "video_id": vid,
                    "text_original": (
                        "injected template" if i < 10 else "source discussion"
                    ),
                    "text_normalized": (
                        "injected template" if i < 10 else "source discussion"
                    ),
                    "published_at": f"2026-10-01T10:{i:02}:00Z",
                    "updated_at": "2026-10-01T12:00:00Z",
                    "like_count": i,
                    "reply_count": 2,
                    "retrieval_timestamp": "2026-10-04T05:00:00Z",
                }
                for i in range(20)
            ],
            "pool_exhausted",
        )


class FixtureLocal:
    def relevance(self, text, category):
        return {
            "news_relevance": True,
            "news_relevance_confidence": 0.95,
            "relevance_method": "fixture",
        }

    def language(self, text):
        return {"language": "en", "confidence": 1}

    def embed(self, texts):
        return [[0.0, 1.0] if "injected" in t else [1.0, 0.0] for t in texts]


class FixtureClassifier:
    def translate(self, text):
        return {
            "parsed": {"text_english": text, "source_language": "en"},
            "model_version": "fixture",
            "classification_timestamp": "2026-10-04T00:00:00Z",
        }

    def classify(self, text):
        x = label()
        x["primary_narrative"] = (
            "foreign_interference" if "injected" in text else "corruption"
        )
        return {
            "parsed": validate_classification(x),
            "model_provider": "fixture",
            "model_name": "fixture",
            "model_version": "fixture-only",
            "prompt_version": "sfi-1.0",
            "taxonomy_version": "narratives-1.0",
            "classifier_version": "classifier-1.0",
            "classification_timestamp": "2026-10-04T05:00:00Z",
        }


class IntegrationTests(unittest.TestCase):
    def pipeline(self, store):
        return Pipeline(
            store,
            datetime.fromisoformat("2026-10-04T05:00:00Z"),
            FixtureYouTube(),
            FixtureLocal(),
            FixtureClassifier(),
        )

    def test_complete_fixture_pipeline_restart_and_launch_gate(self):
        store = MemoryStore()
        result = self.pipeline(store).run()
        self.assertEqual(result["status"], "awaiting_validation")
        snapshots = store.read("dashboard_snapshots")
        self.assertEqual(len(snapshots), 1)
        self.assertGreater(len(snapshots[0]["payload"]["videos"]), 0)
        for video in snapshots[0]["payload"]["videos"]:
            self.assertEqual(video["injection"], 0.5)
            self.assertEqual(video["comments_analyzed"], 20)
            self.assertIsNotNone(video["aai"])
        self.assertTrue(store.read("cross_video_clusters"))
        self.assertTrue(store.read("human_validation"))
        self.assertEqual(len(store.read("candidate_videos")), 9)
        before = copy.deepcopy(store.tables)
        self.pipeline(store).run()
        self.assertEqual(store.tables, before)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.json"
            store.progress = lambda: {
                "batches": [{"id": result["batch"], "candidates": 9}],
                "coverage": [],
            }
            export_public(store, p)
            out = json.loads(p.read_text())
            self.assertEqual(out["videos"], [])
            self.assertEqual(out["mode"], "empty")
            self.assertEqual(out["collection"]["batches"][0]["candidates"], 9)
            self.assertEqual(out["candidates"], [])
            self.assertNotIn("source_observation", p.read_text())

    def test_failure_restart_after_sampling_preserves_draw(self):
        store = MemoryStore()
        pipe = self.pipeline(store)

        def fail(*args):
            raise RuntimeError("simulated outage")

        pipe.yt.comments = fail
        with self.assertRaises(RuntimeError):
            pipe.run()
        sample = copy.deepcopy(store.read("sampled_videos"))
        self.assertEqual(store.batches[pipe.id]["status"], "failed")
        result = self.pipeline(store).run()
        self.assertEqual(result["status"], "awaiting_validation")
        self.assertEqual(store.read("sampled_videos"), sample)

    def test_versioned_correction_keeps_source_sample_and_original_snapshot(self):
        store = MemoryStore()
        original = self.pipeline(store)
        original.run()
        before = copy.deepcopy(store.read("dashboard_snapshots", original.id))
        sample = [r["payload"] for r in store.read("sampled_videos", original.id)]
        correction = Pipeline(
            store,
            datetime.fromisoformat("2026-10-04T05:00:00Z"),
            FixtureYouTube(),
            FixtureLocal(),
            FixtureClassifier(),
            revision="correction-1",
        )
        result = correction.run()
        self.assertEqual(result["status"], "awaiting_validation")
        self.assertEqual(store.read("dashboard_snapshots", original.id), before)
        self.assertEqual(
            [r["payload"] for r in store.read("sampled_videos", correction.id)], sample
        )
