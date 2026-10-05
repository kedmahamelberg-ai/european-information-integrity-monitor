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
        "topics": ["military_defence"],
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
        "content_reference": {
            "summary": "The narrator calls for defence preparation and condemns an attack.",
            "evidence": {"quote": "This attack is awful.", "source_id": "transcript:0"},
        },
        "confidence": 0.8,
        "comments": [
            {
                "comment_id": "c",
                "alignment": "supports",
                "stance_target": "The narrator’s condemnation of the attack",
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

    def test_combined_imagery_requires_transcript_evidence(self):
        x = label()
        imagery = next(e for e in x["execution"] if e["category"] == "imagery_visual")
        imagery["status"] = "present"
        with self.assertRaises(ValueError):
            validate_label(x, document())
        doc = document()
        doc["sections"].append(
            {
                "id": "transcript:1",
                "text": "A white line glows on the empty square under the lamps.",
            }
        )
        imagery.update(
            evidence={
                "source_id": "transcript:1",
                "quote": "A white line glows on the empty square",
            },
            rationale="Descriptive narration creates a mental picture.",
        )
        validate_label(x, doc)
        self.assertEqual(len(x["execution"]), 5)
        self.assertNotIn("verbal_imagery", config("hybrid")["execution"])

    def test_resource_topic_does_not_require_military_role(self):
        x, doc = label(), document()
        doc["sections"].append(
            {
                "id": "transcript:1",
                "text": "Our groundwater is unsafe and its quantity is not infinite.",
            }
        )
        x.update(
            topics=["water"],
            roles=[],
            evidence={
                "source_id": "transcript:1",
                "quote": "Our groundwater is unsafe",
            },
        )
        validate_label(x, doc)
        self.assertNotIn("context", schema()["properties"])
        self.assertNotIn("domains", schema()["properties"])

    def test_neutral_video_allows_comment_stance(self):
        from eiim.hybrid import validate_comments
        from eiim.hybrid_review import video_values

        x, doc = label(), document()
        doc["sections"][0]["text"] = "The deployment began today."
        x.update(topics=[], roles=[], relevance="not_related")
        x["evidence"] = {"quote": "", "source_id": ""}
        x["content_reference"] = {
            "summary": "A deployment began today.",
            "evidence": {
                "quote": "The deployment began today.",
                "source_id": "transcript:0",
            },
        }
        for e in x["execution"]:
            e["status"] = "not_applicable"
        x["comments"][0].update(
            alignment="opposes",
            stance_target="The deployment",
            rationale="Rejects the deployment as reckless.",
        )
        doc["comments"][0]["text_english"] = "That deployment is reckless."
        validate_label(x, doc)
        validate_comments(
            {"comments": x["comments"]},
            dict(doc, content_reference=x["content_reference"]),
        )
        self.assertNotIn("stance", schema()["properties"])
        self.assertNotIn("stance", video_values(x))

    def test_stance_requires_target_and_rejects_retired_gate(self):
        x = label()
        x["comments"][0]["stance_target"] = ""
        with self.assertRaises(ValueError):
            validate_label(x, document())
        x["comments"][0]["alignment"] = "no_video_stance"
        with self.assertRaises(ValueError):
            validate_label(x, document())
        x["comments"][0]["alignment"] = "unclear"
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
        x.update(relevance="not_related")
        with self.assertRaises(ValueError):
            validate_label(x, document())
        x.update(topics=[], roles=[])
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

    def test_counter_refresh_preserves_source_and_uses_actual_snapshot(self):
        from eiim.hybrid import refresh_engagement
        from eiim.engagement import engagement

        s = HybridTests().make_transcript_store()
        old = copy.deepcopy(s.read("candidate_videos"))

        class API:
            def get(self, resource, **kw):
                assert (
                    resource == "videos"
                    and kw["id"] == "v"
                    and kw["part"] == "statistics"
                )
                return {
                    "items": [
                        {
                            "id": "v",
                            "statistics": {"viewCount": "123", "likeCount": "4"},
                        }
                    ]
                }

        refresh_engagement(s, "2026-W40", API())
        source = retained_inputs(s, "2026-W40")[0]["v"][0]
        self.assertEqual(engagement(source)["views"], 123)
        self.assertIsNone(engagement(source)["total_comments"])
        self.assertEqual(s.read("candidate_videos"), old)
        self.assertFalse(s.read("comments"))

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
        item["human_label"]["execution:imagery_visual"] = "absent_after_watching"
        item["decisions"]["execution:imagery_visual"] = "disagree"
        with self.assertRaises(ValueError):
            validate_review(item, row)
        item["basis"] = "watched_video"
        validate_review(item, row)

    def test_forged_agreement_rejected(self):
        from eiim.hybrid_review import validate_review

        item, row = self.review()
        item["human_label"]["topics"] = ["energy"]
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


class StagedCommentTests(unittest.TestCase):
    def test_comments_batched_independently_and_coverage_preserved(self):
        s = HybridTests().make_transcript_store()
        s.batch({"id": "2026-W40"}, "test")
        records = []
        for n in range(7):
            cid = "c" + str(n)
            records += [
                record(
                    "comments",
                    "2026-W40",
                    cid,
                    {
                        "comment_id": cid,
                        "video_id": "v",
                        "text_original": "That attack is awful",
                    },
                    "v",
                ),
                record(
                    "pipeline_runs",
                    "2026-W40",
                    "translation:" + cid,
                    {
                        "comment_translation_id": cid,
                        "text_english": "That attack is awful",
                    },
                    "v",
                ),
            ]
        s.write("2026-W40", records)

        class Fake:
            cfg = {"model": "test"}
            sizes = []

            def request(self, text, prompt, shape, kind):
                doc = json.loads(text)
                if kind == "hybrid":
                    assert (
                        "CONTENT REFERENCE." in prompt and "imagery_visual:" in prompt
                    )
                    self.sizes.append(("video", len(doc["comments"])))
                    x = label()
                    x["comments"] = []
                else:
                    self.sizes.append(("comments", len(doc["comments"])))
                    assert "stance" not in doc
                    assert doc["sections"] and doc["content_reference"]["summary"]
                    x = {
                        "comments": [
                            {**label()["comments"][0], "comment_id": c["comment_id"]}
                            for c in doc["comments"]
                        ]
                    }
                return {
                    "parsed": x,
                    "model_name": "test",
                    "model_version": "test",
                    "classification_timestamp": "2026-10-04T00:00:00Z",
                }

        f = Fake()
        result = reclassify(s, "2026-W40", f)
        self.assertEqual(f.sizes, [("video", 0), ("comments", 5), ("comments", 2)])
        self.assertEqual(result["classified_comments"], 7)

    def test_missing_ids_rejected_without_losing_other_results(self):
        from eiim.hybrid import validate_comments

        doc = {
            "content_reference": label()["content_reference"],
            "comments": [{"comment_id": "c"}, {"comment_id": "d"}],
        }
        with self.assertRaises(ValueError):
            validate_comments({"comments": label()["comments"]}, doc)


class PublicationAuditTests(unittest.TestCase):
    def test_random_audit_unlocks_ai_labels_without_claiming_individual_review(self):
        from eiim.hybrid import VERSION
        from eiim.hybrid_review import video_values
        from eiim.hybrid_public import export_public
        from tempfile import TemporaryDirectory
        from pathlib import Path

        s = HybridTests().make_transcript_store()
        s.batch({"id": "2026-W40"}, "test")
        rows = []
        for vid in ["v", "other"]:
            if vid != "v":
                for t in ["candidate_videos", "sampled_videos", "pipeline_runs"]:
                    for r in list(s.read(t, "2026-W40")):
                        p = copy.deepcopy(r["payload"])
                        p["video_id"] = vid
                        if "english_access_video_id" in p:
                            p["english_access_video_id"] = vid
                        rows.append(record(t, "2026-W40", r["id"] + ":other", p, vid))
            p = {
                "hybrid_version": VERSION,
                "video_id": vid,
                "label": label(),
                "classified_at": "2026-10-04T00:00:00Z",
                "model_version": "test",
                "transcript_truncated": False,
            }
            rows.append(record("pipeline_runs", "2026-W40", "label:" + vid, p, vid))
        s.write("2026-W40", rows)
        q = next(r for r in s.read("pipeline_runs") if r["id"] == "label:v")
        h = {
            "version": VERSION,
            "hybrid_version": VERSION,
            "queue_record_id": q["id"],
            "queue_hash": q["payload_hash"],
            "reviewer": "Test",
            "reviewed_at": "2026-10-04T00:00:00Z",
            "basis": "english_transcript",
            "item_type": "hybrid_video",
            "human_label": video_values(label()),
            "decisions": {k: "agree" for k in video_values(label())},
            "review_status": "complete",
        }
        s.write(
            "2026-W40", [record("human_validation", "2026-W40", "review:v", h, "v")]
        )
        with (
            TemporaryDirectory() as d,
            patch(
                "eiim.hybrid_public.sample_plan",
                return_value={"target": 1, "selected_video_ids": ["v"]},
            ),
        ):
            p = Path(d) / "data.json"
            export_public(s, p)
            out = json.loads(p.read_text())
        self.assertTrue(out["batches"][0]["audit_complete"])
        other = next(x for x in out["videos"] if x["id"] == "other")
        self.assertEqual(other["classification_status"], "ai_coded_sample_audited")
        self.assertIsNotNone(other["label"])
        self.assertEqual(out["collection"]["reviewed_videos"], 1)
