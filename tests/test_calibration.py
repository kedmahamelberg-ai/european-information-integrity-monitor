import copy
import unittest
from unittest.mock import patch
from eiim.core import digest
from eiim.storage import MemoryStore, record
from eiim.hybrid import VERSION
from eiim.hybrid_review import video_values
from eiim.calibration import (
    project_four_categories,
    current_reviews,
    calibration_examples,
)
from test_hybrid import label


class CalibrationTests(unittest.TestCase):
    def fixture(self):
        s = MemoryStore()
        x = label()
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
        self.assertEqual(migrated["version"], VERSION)
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
