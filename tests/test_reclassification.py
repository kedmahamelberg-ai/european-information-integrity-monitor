import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from eiim.core import config
from eiim.reclassification import (
    DIMENSIONS,
    VERSION,
    evidence_input,
    validate_evidence_label,
    reclassify,
)
from eiim.review import prepare_review_items, model_values
from eiim.cli import import_reviews
from eiim.storage import MemoryStore
from eiim.research import agreement, validation_gate
import test_pipeline


def response(status="scored", scores=(0, 0, 0)):
    return dict(
        zip(DIMENSIONS, scores),
        targets=[],
        countries=[],
        direction="unclear",
        primary_narrative="none_unclear",
        secondary_narratives=[],
        other_narrative_label=None,
        other_narrative_explanation=None,
        confidence=0.8,
        narrative_confidence=0.7,
        short_rationale="Synthetic fixture, not empirical validation.",
        assessment_status=status,
        public_affairs_relevance="in_scope",
        publisher_stance="asserted",
        dimension_evidence=[
            dict(
                dimension=k,
                quote="",
                source_id="",
                target="",
                speaker="",
                attribution="none",
                explanation="No evidence for this dimension in the fixture.",
            )
            for k in DIMENSIONS
        ],
    )


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = evidence_input(
            {"title": "I feel distant from the opposition.", "description": ""}, {}
        )

    def positive(self):
        r = response(scores=(1, 0, 0))
        r["targets"] = [
            dict(target_name="opposition", target_type="political", direction="unclear")
        ]
        r["dimension_evidence"][0].update(
            quote="I feel distant from the opposition.",
            source_id="title",
            target="opposition",
            speaker="speaker",
            attribution="author_assertion",
        )
        return r

    def test_social_distance_does_not_require_aversion(self):
        r = validate_evidence_label(self.positive(), self.doc)
        self.assertEqual(r["othering"], 1)
        self.assertEqual(r["targets"][0]["direction"], "unclear")
        self.assertFalse(r["strong_sectarian_frame"])

    def test_ungrounded_or_reported_positive_rejected(self):
        for changes in [
            {"quote": "Invented words"},
            {"source_id": "missing"},
            {"target": "another target"},
            {"attribution": "reported_only"},
            {"attribution": "rejected"},
            {"quote": ""},
        ]:
            r = self.positive()
            r["dimension_evidence"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_evidence_label(r, self.doc)

    def test_aversion_requires_negative_evidence_target_not_other_target(self):
        r = self.positive()
        r.update(othering=0, aversion=1)
        r["targets"].append(
            dict(
                target_name="government", target_type="political", direction="negative"
            )
        )
        r["dimension_evidence"][1].update(
            r["dimension_evidence"][0], dimension="aversion"
        )
        with self.assertRaises(ValueError):
            validate_evidence_label(r, self.doc)

    def test_abstention_is_null_not_zero_and_not_agreement_denominator(self):
        r = response("insufficient_evidence", (None, None, None))
        result = validate_evidence_label(r, self.doc)
        self.assertIsNone(result["sfi"])
        self.assertIsNone(result["strong_sectarian_frame"])
        self.assertEqual(
            agreement([dict(item_type="video", human_label=r, model_label=r)])["n"], 0
        )
        r["othering"] = 0
        with self.assertRaises(ValueError):
            validate_evidence_label(r, self.doc)

    def test_actual_transcript_included_and_missing_not_invented(self):
        self.assertEqual(self.doc["scope"], "metadata_only")
        doc = evidence_input(
            {"title": "Discussion"},
            {
                "transcript_english": [
                    dict(text="First line", start=1),
                    dict(text="second line", start=3),
                ]
            },
        )
        self.assertEqual(doc["scope"], "metadata_and_english_transcript")
        self.assertEqual(doc["sections"][-1]["text"], "First line second line")
        self.assertFalse(doc["transcript_truncated"])

    def test_truncation_disclosed(self):
        doc = evidence_input(
            {},
            {
                "transcript_english": [
                    dict(text="a" * 40000, start=0),
                    dict(text="b" * 40000, start=50),
                ]
            },
        )
        self.assertTrue(doc["transcript_truncated"])
        self.assertEqual(doc["transcript_segments_included"], 1)


class CandidateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        test_pipeline.IntegrationTests().pipeline(self.store).run()
        self.batch = self.store.read("weekly_batches")[0]["id"]
        prepare_review_items(self.store, self.batch)

    def classifier(self):
        def request(text, prompt, shape, kind):
            parsed = validate_evidence_label(
                response("insufficient_evidence", (None, None, None)), json.loads(text)
            )
            return dict(
                parsed=parsed,
                model_provider="fixture",
                model_name="fixture",
                model_version="fixture",
                prompt_version="sfi-1.1",
                taxonomy_version="narratives-1.0",
                classifier_version=VERSION,
                classification_timestamp="2026-10-04T18:00:00Z",
            )

        return SimpleNamespace(cfg=config("models"), request=request)

    def test_recode_preserves_baseline_and_restart_and_replaces_queue_display(self):
        baseline = copy.deepcopy(self.store.read("video_classifications"))
        first = reclassify(self.store, self.batch, self.classifier())
        second = reclassify(self.store, self.batch, self.classifier())
        self.assertGreater(first["total"], 0)
        self.assertEqual(second["newly_classified"], 0)
        self.assertEqual(baseline, self.store.read("video_classifications"))
        items = [
            i
            for i in prepare_review_items(self.store, self.batch)
            if i["item_type"] == "video"
        ]
        self.assertEqual(len(items), first["total"])
        self.assertTrue(all(i["classifier_version"] == VERSION for i in items))

    def test_import_abstention_preserves_it_and_does_not_satisfy_launch_gate(self):
        reclassify(self.store, self.batch, self.classifier())
        item = next(
            i
            for i in prepare_review_items(self.store, self.batch)
            if i["item_type"] == "video"
        )
        review = dict(
            queue_record_id=item["queue_record_id"],
            queue_hash=item["queue_hash"],
            human_label=item["ai_values"],
            review_decisions={k: "agree" for k in item["ai_values"]},
            reviewer="Fixture",
            reviewed_at="2026-10-04T19:00:00Z",
            review_method="ai_assisted_confirmation",
            review_evidence_basis="metadata_only",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "reviews.json"
            path.write_text(json.dumps([review]))
            self.assertEqual(import_reviews(self.store, path)["imported_reviews"], 1)
        rows = [r["payload"] for r in self.store.read("human_validation")]
        self.assertEqual(validation_gate(rows, VERSION)["videos_reviewed"], 0)
        completed = next(r for r in rows if r["review_status"] == "complete")
        self.assertIsNone(completed["human_label"]["othering"])
        self.assertEqual(completed["review_evidence_basis"], "metadata_only")
