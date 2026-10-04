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
    classify_document,
    validate_source_screen,
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

    def test_six_point_scale_rejects_out_of_range_and_preserves_legacy(self):
        from eiim.core import sfi

        r = self.positive()
        r["othering"] = 6
        result = validate_evidence_label(r, self.doc)
        self.assertEqual(result["sfi"], 2)
        self.assertEqual(result["score_max"], 6)
        self.assertTrue(sfi(3, 3, 3, score_max=6)[1])
        self.assertFalse(sfi(2, 3, 3, score_max=6)[1])
        with self.assertRaises(ValueError):
            sfi(6, 0, 0)
        r["othering"] = 7
        with self.assertRaises(ValueError):
            validate_evidence_label(r, self.doc)

    def test_agreement_never_pools_different_scales(self):
        rows = []
        for maximum in (4, 6):
            label = dict(
                othering=maximum,
                aversion=0,
                moralization=0,
                narratives=[],
                targets=[],
                score_max=maximum,
            )
            rows.append(dict(item_type="video", model_label=label, human_label=label))
        report = agreement(rows)
        self.assertFalse(report["pooled"])
        self.assertEqual(
            len(
                report["by_scale"]["6"]["dimension_diagnostics"]["othering"][
                    "confusion_rows_human_columns_model"
                ]
            ),
            7,
        )
        self.assertEqual(
            len(
                report["by_scale"]["4"]["dimension_diagnostics"]["othering"][
                    "confusion_rows_human_columns_model"
                ]
            ),
            5,
        )

    def test_social_distance_does_not_require_aversion(self):
        r = validate_evidence_label(self.positive(), self.doc)
        self.assertEqual(r["othering"], 1)
        self.assertEqual(r["targets"][0]["direction"], "unclear")
        self.assertFalse(r["strong_sectarian_frame"])

    def test_ungrounded_or_reported_positive_rejected(self):
        for changes in [
            {"quote": "Invented words"},
            {"target": "another target"},
            {"attribution": "reported_only"},
            {"attribution": "rejected"},
            {"quote": ""},
        ]:
            r = self.positive()
            r["dimension_evidence"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_evidence_label(r, self.doc)

    def test_caption_locator_can_be_repaired_only_for_unchanged_exact_quote(self):
        r = self.positive()
        r["dimension_evidence"][0]["source_id"] = "invented-range"
        fixed = validate_evidence_label(r, self.doc)
        self.assertEqual(fixed["dimension_evidence"][0]["source_id"], "title")
        self.assertEqual(
            fixed["dimension_evidence"][0]["model_source_id"], "invented-range"
        )
        self.assertEqual(
            fixed["dimension_evidence"][0]["quote"], r["dimension_evidence"][0]["quote"]
        )

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

    def test_zero_heavy_agreement_does_not_hide_zero_recall(self):
        neutral = dict(
            othering=0, aversion=0, moralization=0, narratives=[], targets=[]
        )
        rows = [
            dict(item_type="video", model_label=neutral, human_label=neutral)
            for _ in range(9)
        ]
        rows.append(
            dict(
                item_type="video",
                model_label=neutral,
                human_label=dict(neutral, othering=1),
                review_evidence_basis="watched_video",
            )
        )
        report = agreement(rows)
        self.assertEqual(report["dimension_agreement"]["othering"], 0.9)
        self.assertEqual(
            report["dimension_diagnostics"]["othering"]["nonzero_recall"], 0
        )
        self.assertIsNone(report["dimension_diagnostics"]["aversion"]["nonzero_recall"])
        self.assertEqual(report["evidence_basis_counts"]["different_or_partial"], 1)

    def test_substantive_neutral_gate_routes_to_integer_only_scoring(self):
        calls = []

        def request(text, prompt, shape, kind):
            calls.append(kind)
            if kind == "source_screen":
                parsed = dict(
                    assessment_status="scored",
                    evidence_quote="I feel distant from the opposition.",
                    source_id="title",
                    explanation="Substantive public-affairs statement.",
                    confidence=0.9,
                )
            else:
                self.assertEqual(
                    shape["properties"]["assessment_status"]["enum"], ["scored"]
                )
                self.assertEqual(shape["properties"]["othering"]["type"], "integer")
                parsed = response()
            return dict(parsed=parsed)

        result = classify_document(
            SimpleNamespace(request=request, cfg={}, batch="fixture"), self.doc
        )
        self.assertEqual(calls, ["source_screen", "sfi_review"])
        self.assertEqual(result["parsed"]["othering"], 0)

    def test_independent_cue_check_retains_pre_audit_scores(self):
        calls = []

        def request(text, prompt, shape, kind):
            calls.append(kind)
            if kind == "source_screen":
                parsed = dict(
                    assessment_status="scored",
                    evidence_quote=self.doc["sections"][0]["text"],
                    source_id="title",
                    explanation="Complete opinion.",
                    confidence=0.9,
                )
            elif kind == "sfi_review":
                parsed = self.positive()
            else:
                parsed = dict(
                    supported=False,
                    quote="",
                    source_id="",
                    explanation="Synthetic rejection to verify independent-check plumbing.",
                )
            return dict(parsed=parsed)

        result = classify_document(
            SimpleNamespace(request=request, cfg={}, batch="fixture"), self.doc
        )["parsed"]
        self.assertEqual(calls, ["source_screen", "sfi_review", "cue_check"])
        self.assertEqual(result["othering"], 0)
        self.assertEqual(result["pre_audit_scores"]["othering"], 1)
        self.assertEqual(result["sfi"], 0)

    def test_screen_requires_real_substantive_quote_for_scored(self):
        valid = dict(
            assessment_status="scored",
            evidence_quote=self.doc["sections"][0]["text"],
            source_id="title",
            explanation="A proposition is present.",
            confidence=0.8,
        )
        self.assertEqual(
            validate_source_screen(valid, self.doc)["assessment_status"], "scored"
        )
        for quote in ["", "Fabricated passage"]:
            with self.assertRaises(ValueError):
                validate_source_screen(dict(valid, evidence_quote=quote), self.doc)


class CandidateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        test_pipeline.IntegrationTests().pipeline(self.store).run()
        self.batch = self.store.read("weekly_batches")[0]["id"]
        prepare_review_items(self.store, self.batch)

    def classifier(self):
        def request(text, prompt, shape, kind):
            self.assertEqual(kind, "source_screen")
            parsed = dict(
                assessment_status="insufficient_evidence",
                explanation="Synthetic source-screen abstention.",
                evidence_quote="",
                source_id="",
                confidence=0.6,
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

        return SimpleNamespace(cfg=config("models"), request=request, batch=self.batch)

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
        self.assertTrue(all(i["score_max"] == 6 for i in items))

    def test_human_six_point_correction_import_and_wrong_scale_rejection(self):
        reclassify(self.store, self.batch, self.classifier())
        item = next(
            i
            for i in prepare_review_items(self.store, self.batch)
            if i["item_type"] == "video"
        )
        human = dict(item["ai_values"], othering=6, aversion=5, moralization=4)
        review = dict(
            queue_record_id=item["queue_record_id"],
            queue_hash=item["queue_hash"],
            human_label=human,
            reviewer="Fixture",
            reviewed_at="2026-10-04T20:00:00Z",
            score_max=6,
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "review.json"
            path.write_text(json.dumps([review]))
            self.assertEqual(import_reviews(self.store, path)["imported_reviews"], 1)
            for changed in (
                dict(review, score_max=4),
                dict(review, human_label=dict(human, othering=7)),
            ):
                path.write_text(json.dumps([changed]))
                with self.assertRaises(ValueError):
                    import_reviews(self.store, path)
        saved = next(
            r["payload"]
            for r in self.store.read("human_validation")
            if r["payload"].get("review_status") == "complete"
        )
        self.assertEqual(saved["human_label"]["othering"], 6)
        self.assertEqual(saved["human_label"]["score_max"], 6)

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
