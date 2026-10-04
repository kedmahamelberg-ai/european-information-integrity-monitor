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

    def test_english_audio_without_transcript_excluded(self):
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

    def test_restart_does_not_reclassify_or_collect(self):
        s = self.test_english_audio_without_transcript_excluded()
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
