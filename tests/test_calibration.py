import copy
import unittest
from unittest.mock import patch
from eiim.core import digest
from eiim.storage import MemoryStore, record
from eiim.hybrid import VERSION
from eiim.hybrid_review import video_values
from eiim.calibration import (
    _balanced_reviews,
    project_four_categories,
    current_reviews,
    calibration_examples,
)
from test_hybrid import label


class CalibrationTests(unittest.TestCase):
    def fixture(self):
        s = MemoryStore()
        s.batch(
            {
                "id": "b",
                "collection_timestamp": "2026-10-05T00:00:00Z",
            },
            "config",
        )
        x = label()
        # The archived 1.3 fixture predates viewpoint-aware coding.
        x.pop("viewpoint_structure")
        x.pop("viewpoints")
        for comment in x["comments"]:
            comment.pop("viewpoint_ids")
        x["execution"].append(
            {
                "category": "imagery_visual",
                "status": "present",
                "evidence": {"quote": "We must prepare", "source_id": "transcript:0"},
                "rationale": "Archived",
            }
        )
        p = {
            "hybrid_version": "hybrid-framing-1.3",
            "label": x,
            "classified_at": "2026-10-05T00:00:00Z",
        }
        old = record("pipeline_runs", "b", "old", p, "v")
        values = video_values(x)
        values["execution:entertainment"] = "present"
        values["reference:speaker_sentiment"] = "positive"
        decisions = {k: "agree" for k in values}
        decisions["execution:entertainment"] = "disagree"
        decisions["reference:speaker_sentiment"] = "disagree"
        review = {
            "version": "hybrid-framing-1.3",
            "hybrid_version": "hybrid-framing-1.3",
            "queue_record_id": "old",
            "queue_hash": old["record"]["payload_hash"],
            "review_status": "complete",
            "item_type": "hybrid_video",
            "comment_id": None,
            "reviewer": "Human",
            "reviewed_at": "2026-10-05T01:00:00Z",
            "basis": "watched_video",
            "human_label": values,
            "decisions": decisions,
        }
        s.write("b", [old, record("human_validation", "b", "review", review, "v")])
        inputs = (
            {
                "v": (
                    {"title": "Narrated historical battle"},
                    {"transcript_english": [{"text": "We must prepare our defence."}]},
                )
            },
            [],
            {},
            [],
        )
        return s, review, inputs

    def test_projection_keeps_human_decisions_and_original_hashes(self):
        s, review, inputs = self.fixture()
        before = copy.deepcopy(s.tables)
        with patch("eiim.hybrid.retained_inputs", return_value=inputs):
            self.assertEqual(project_four_categories(s, "b")["preserved_reviews"], 1)
            n = len(s.read("pipeline_runs"))
            project_four_categories(s, "b")
            self.assertEqual(len(s.read("pipeline_runs")), n)
        self.assertEqual(
            s.tables["pipeline_runs"]["old"], before["pipeline_runs"]["old"]
        )
        self.assertEqual(
            s.tables["human_validation"]["review"], before["human_validation"]["review"]
        )
        migrated = next(iter(current_reviews(s).values()))
        expected = dict(review["human_label"])
        expected.pop("execution:imagery_visual")
        self.assertEqual(migrated["human_label"], expected)
        self.assertEqual(migrated["reviewed_at"], review["reviewed_at"])
        self.assertEqual(migrated["schema_projection"]["from_review"], "review")
        self.assertEqual(migrated["version"], "hybrid-framing-1.4")
        self.assertEqual(migrated["human_label"]["execution:entertainment"], "present")

    def test_invalid_hash_does_not_become_a_confirmed_review(self):
        s, review, inputs = self.fixture()
        s.tables["human_validation"]["review"]["payload"]["queue_hash"] = "tampered"
        with patch("eiim.hybrid.retained_inputs", return_value=inputs):
            with self.assertRaisesRegex(ValueError, "version/hash"):
                project_four_categories(s, "b")
        self.assertEqual(len(s.read("pipeline_runs")), 1)

    def test_calibration_examples_exclude_self_and_keep_human_source(self):
        s, review, inputs = self.fixture()
        with patch("eiim.hybrid.retained_inputs", return_value=inputs):
            project_four_categories(s, "b")
            ex = calibration_examples(s)
            self.assertEqual(
                ex["videos"][0]["human_label"]["execution:entertainment"], "present"
            )
            self.assertEqual(ex["videos"][0]["reviewer"], "Human")
            self.assertEqual(
                ex["videos"][0]["reference"]["speaker_sentiment"], "positive"
            )
            self.assertNotIn("execution:imagery_visual", ex["videos"][0]["human_label"])
            self.assertEqual(
                calibration_examples(s, exclude_video_id="v"),
                {"videos": [], "comments": []},
            )

    def test_calibration_reads_large_tables_one_retained_batch_at_a_time(self):
        s, review, inputs = self.fixture()
        with patch("eiim.hybrid.retained_inputs", return_value=inputs):
            project_four_categories(s, "b")
            with patch.object(s, "read", wraps=s.read) as read:
                calibration_examples(s)
        calls = [call.args for call in read.call_args_list]
        self.assertNotIn(("pipeline_runs",), calls)
        self.assertNotIn(("human_validation",), calls)
        self.assertIn(("pipeline_runs", "b"), calls)
        self.assertIn(("human_validation", "b"), calls)

    def test_corrected_examples_retain_cross_batch_coverage(self):
        known = {
            "w40-video": {"batch_id": "2026-W40"},
            "w41-video": {"batch_id": "2026-W41"},
            "w41-newer": {"batch_id": "2026-W41"},
        }
        reviews = {
            ("w40-video", None): {
                "queue_record_id": "w40-video",
                "comment_id": None,
                "reviewed_at": "2026-10-05T10:00:00Z",
                "decisions": {"relevance": "disagree"},
            },
            ("w41-video", None): {
                "queue_record_id": "w41-video",
                "comment_id": None,
                "reviewed_at": "2026-10-11T10:00:00Z",
                "decisions": {"relevance": "disagree"},
            },
            ("w41-newer", None): {
                "queue_record_id": "w41-newer",
                "comment_id": None,
                "reviewed_at": "2026-10-11T11:00:00Z",
                "decisions": {"relevance": "disagree", "topics": "disagree"},
            },
        }
        selected = _balanced_reviews(reviews, known, comments=False, limit=4)
        first_batches = {
            known[review["queue_record_id"]]["batch_id"] for review in selected[:2]
        }
        self.assertEqual(first_batches, {"2026-W40", "2026-W41"})
