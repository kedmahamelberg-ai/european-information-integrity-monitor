import copy
import json
import unittest
from unittest.mock import patch
from eiim.hybrid import validate_label, retained_inputs, reclassify, schema
from eiim.storage import MemoryStore, record
from eiim.core import config


def document():
    return {
        "sections": [
            {
                "id": "transcript:0",
                "text": "We must prepare our defence. This attack is awful.",
            }
        ],
        "comments": [{"comment_id": "c", "text_english": "This attack is awful."}],
        "transcript_truncated": False,
    }


def label():
    return {
        "relevance": "related",
        "context": "current",
        "domains": ["defence_readiness"],
        "evidence_status": "reported",
        "evidence": {
            "quote": "We must prepare our defence.",
            "source_id": "transcript:0",
        },
        "rationale": "Defensive preparation is discussed.",
        "roles": [
            {
                "entity": "France",
                "entity_code": "FR",
                "role": "readiness",
                "evidence": {
                    "quote": "We must prepare our defence.",
                    "source_id": "transcript:0",
                },
                "rationale": "Example identified speaker.",
            }
        ],
        "stance": {
            "status": "expressed",
            "proposition": "The attack is awful.",
            "attribution": "Narrator",
            "evidence": {"quote": "This attack is awful.", "source_id": "transcript:0"},
        },
        "confidence": 0.8,
        "comments": [
            {
                "comment_id": "c",
                "alignment": "supports",
                "sentiment": "negative",
                "sentiment_target": "attack",
                "rationale": "Condemns the same attack.",
            }
        ],
        "execution": [
            {
                "category": c,
                "status": "not_observable",
                "evidence": {"quote": "", "source_id": ""},
                "rationale": "Insufficient modality.",
            }
            for c in config("hybrid")["execution"]
        ],
    }


class HybridTests(unittest.TestCase):
    def test_negative_sentiment_can_support(self):
        self.assertEqual(
            validate_label(label(), document())["comments"][0]["alignment"], "supports"
        )

    def test_role_requires_exact_evidence(self):
        x = label()
        x["roles"][0]["evidence"]["quote"] = "invented"
        with self.assertRaises(ValueError):
            validate_label(x, document())

    def test_visuals_not_guessed_from_transcript(self):
        x = label()
        x["execution"][3]["status"] = "present"
        with self.assertRaises(ValueError):
            validate_label(x, document())

    def test_no_stance_cannot_have_agreement(self):
        x = label()
        x["stance"]["status"] = "no_stance"
        with self.assertRaises(ValueError):
            validate_label(x, document())
        x["comments"][0]["alignment"] = "no_video_stance"
        validate_label(x, document())

    def test_every_comment_exactly_once(self):
        for comments in [
            [],
            label()["comments"] * 2,
            [{**label()["comments"][0], "comment_id": "other"}],
        ]:
            x = label()
            x["comments"] = comments
            with self.assertRaises(ValueError):
                validate_label(x, document())

    def test_unrelated_no_execution_or_roles(self):
        x = label()
        x.update(relevance="not_related", context="not_applicable")
        with self.assertRaises(ValueError):
            validate_label(x, document())
        x.update(domains=[], roles=[])
        for e in x["execution"]:
            e["status"] = "not_applicable"
        validate_label(x, document())

    def make_transcript_store(self):
        s = MemoryStore()
        batch = "2026-W40"
        s.write(
            batch,
            [
                record(
                    "candidate_videos",
                    batch,
                    "v",
                    {
                        "video_id": "v",
                        "title": "We must prepare our defence.",
                        "original_audio_language": "en",
                    },
                    "v",
                ),
                record(
                    "sampled_videos", batch, "v", {"selected_for_sample": True}, "v"
                ),
            ],
        )
        self.assertFalse(retained_inputs(s, batch)[0])
        s.write(
            batch,
            [
                record(
                    "pipeline_runs",
                    batch,
                    "access",
                    {
                        "english_access_video_id": "v",
                        "policy_version": "english-access-1.0",
                        "eligible": True,
                        "original_language": "en",
                        "transcript_english": [
                            {
                                "text": "We must prepare our defence. This attack is awful.",
                                "start": 0,
                            }
                        ],
                    },
                    "v",
                )
            ],
        )
        self.assertIn("v", retained_inputs(s, batch)[0])
        return s

    def test_english_audio_requires_transcript(self):
        self.make_transcript_store()

    def test_restart_does_not_reclassify_or_collect(self):
        s = self.make_transcript_store()
        s.batch({"id": "2026-W40"}, "test")

        class Fake:
            cfg = {"model": "test"}
            calls = 0

            def request(self, text, prompt, shape, kind):
                self.calls += 1
                x = label()
                x["comments"] = []
                return {
                    "parsed": x,
                    "model_name": "test",
                    "model_version": "test",
                    "classification_timestamp": "2026-10-04T00:00:00Z",
                }

        fake = Fake()
        with patch(
            "eiim.services.YouTube", side_effect=AssertionError("No collection")
        ):
            a = reclassify(s, "2026-W40", fake)
            b = reclassify(s, "2026-W40", fake)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(a["classified_videos"], 1)
        self.assertFalse(b["new_source_collection"])


class EngagementTests(unittest.TestCase):
    def test_missing_is_not_zero(self):
        from eiim.engagement import engagement

        m = engagement(
            {
                "raw_api_response": {
                    "statistics": {"viewCount": "100", "commentCount": "0"}
                }
            }
        )
        self.assertIsNone(m["likes"])
        self.assertIsNone(m["shares"])
        self.assertEqual(m["total_comments"], 0)
        self.assertEqual(m["comments_per_1000_views"], 0)
        self.assertIsNone(m["likes_per_1000_views"])
        self.assertIsNone(
            engagement(
                {
                    "raw_api_response": {
                        "statistics": {"viewCount": "0", "likeCount": "4"}
                    }
                }
            )["likes_per_1000_views"]
        )

    def test_timestamp_and_age(self):
        from eiim.engagement import engagement

        m = engagement(
            {
                "published_at": "2026-10-01T00:00:00Z",
                "retrieved_at": "2026-10-02T00:00:00Z",
                "raw_api_response": {
                    "statistics": {"viewCount": "200", "likeCount": "10"}
                },
            }
        )
        self.assertEqual(m["age_hours_at_capture"], 24)
        self.assertEqual(m["likes_per_1000_views"], 50)


class HumanReviewTests(unittest.TestCase):
    def review(self):
        from eiim.hybrid import VERSION
        from eiim.hybrid_review import video_values
        from eiim.core import digest

        p = {"label": label()}
        row = {"payload": p, "payload_hash": digest(p)}
        values = video_values(p["label"])
        item = {
            "version": VERSION,
            "queue_hash": row["payload_hash"],
            "reviewer": "Tester",
            "reviewed_at": "2026-10-04T00:00:00Z",
            "basis": "english_transcript",
            "item_type": "hybrid_video",
            "human_label": values,
            "decisions": {k: "agree" for k in values},
        }
        return item, row

    def test_all_fields_explicit_and_hash_bound(self):
        from eiim.hybrid_review import validate_review

        item, row = self.review()
        validate_review(item, row)
        item["decisions"].pop("relevance")
        with self.assertRaises(ValueError):
            validate_review(item, row)
        item, row = self.review()
        item["queue_hash"] = "stale"
        with self.assertRaises(ValueError):
            validate_review(item, row)

    def test_visual_judgment_requires_watching(self):
        from eiim.hybrid_review import validate_review

        item, row = self.review()
        item["human_label"]["execution:imagery_visual"] = "present"
        item["decisions"]["execution:imagery_visual"] = "disagree"
        with self.assertRaises(ValueError):
            validate_review(item, row)
        item["basis"] = "watched_video"
        validate_review(item, row)

    def test_forged_agreement_rejected(self):
        from eiim.hybrid_review import validate_review

        item, row = self.review()
        item["human_label"]["context"] = "historical"
        with self.assertRaises(ValueError):
            validate_review(item, row)

    def test_public_allowlist_excludes_raw_comments_and_ai_labels(self):
        from eiim.hybrid_public import export_public
        from eiim.hybrid import VERSION
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from eiim.core import digest

        s = HybridTests().make_transcript_store()
        s.batch({"id": "2026-W40"}, "test")
        p = {
            "hybrid_version": VERSION,
            "video_id": "v",
            "label": label(),
            "classified_at": "2026-10-04T00:00:00Z",
            "model_version": "test",
            "transcript_truncated": False,
        }
        s.write("2026-W40", [record("pipeline_runs", "2026-W40", "hybrid", p, "v")])
        with TemporaryDirectory() as d:
            path = Path(d) / "data.json"
            export_public(s, path)
            out = json.loads(path.read_text())
        self.assertIsNone(out["videos"][0]["label"])
        self.assertNotIn("This attack is awful", json.dumps(out))
        self.assertEqual(out["collection"]["classified_comments"], 1)
