import copy
import json
import tempfile
import unittest
from pathlib import Path
from eiim.core import digest
from eiim.cli import import_reviews
from eiim.review import prepare_review_items, write_review_html
from eiim.research import validation_gate
from eiim.storage import MemoryStore
import test_pipeline


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        test_pipeline.IntegrationTests().pipeline(self.store).run()
        self.items = prepare_review_items(self.store)
        self.video = next(x for x in self.items if x["item_type"] == "video")

    def response(self):
        item = self.video
        return dict(
            queue_record_id=item["queue_record_id"],
            queue_hash=item["queue_hash"],
            human_label=copy.deepcopy(item["ai_values"]),
            review_decisions={k: "agree" for k in item["ai_values"]},
            review_method="ai_assisted_confirmation",
            reviewer="Fixture reviewer",
            reviewed_at="2026-10-04T12:00:00+00:00",
            review_notes="Fixture test",
        )

    def do_import(self, items):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "reviews.json"
            p.write_text(json.dumps(items))
            return import_reviews(self.store, p)

    def test_confirm_and_correct_preserve_model_and_provenance(self):
        before = copy.deepcopy(self.video["model_label"])
        response = self.response()
        response["review_decisions"]["othering"] = "disagree"
        response["human_label"]["othering"] = (
            response["human_label"]["othering"] + 1
        ) % 5
        self.assertEqual(self.do_import([response])["imported_reviews"], 1)
        self.do_import([response])
        complete = [
            r["payload"]
            for r in self.store.read("human_validation")
            if r["payload"]["review_status"] == "complete"
        ]
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0]["model_label"], before)
        self.assertEqual(complete[0]["review_method"], "ai_assisted_confirmation")
        self.assertEqual(complete[0]["review_decisions"]["othering"], "disagree")
        self.assertNotIn(
            self.video["queue_record_id"],
            [x["queue_record_id"] for x in prepare_review_items(self.store)],
        )

    def test_missing_decision_rejects_entire_import(self):
        good = self.response()
        bad = copy.deepcopy(good)
        bad["review_decisions"].pop("aversion")
        with self.assertRaises(ValueError):
            self.do_import([good, bad])
        self.assertFalse(
            any(
                r["payload"]["review_status"] == "complete"
                for r in self.store.read("human_validation")
            )
        )

    def test_later_correction_wins_independent_of_row_order(self):
        first = self.response()
        self.do_import([first])
        corrected = copy.deepcopy(first)
        corrected["reviewed_at"] = "2026-10-04T13:00:00+00:00"
        corrected["review_decisions"]["othering"] = "disagree"
        corrected["human_label"]["othering"] = (
            corrected["human_label"]["othering"] + 1
        ) % 5
        self.do_import([corrected])
        reviews = [r["payload"] for r in self.store.read("human_validation")]
        for ordered in [reviews, list(reversed(reviews))]:
            report = validation_gate(ordered, self.video["classifier_version"])
            self.assertEqual(report["videos_reviewed"], 1)
            self.assertEqual(report["agreement"]["dimension_agreement"]["othering"], 0)

    def test_disagreement_requires_correction_and_hash_is_checked(self):
        response = self.response()
        response["review_decisions"]["othering"] = "disagree"
        with self.assertRaises(ValueError):
            self.do_import([response])
        response = self.response()
        response["queue_hash"] = "tampered"
        with self.assertRaises(ValueError):
            self.do_import([response])

    def test_private_html_escapes_source_and_has_no_credentials(self):
        items = copy.deepcopy(self.items)
        items[0]["source_observation"]["title"] = "</script><script>alert(1)</script>"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "index.html"
            write_review_html(items, path)
            content = path.read_text()
            self.assertNotIn("</script><script>alert(1)</script>", content)
            self.assertIn("\\u003c/script\\u003e", content)
            self.assertIn("youtube-nocookie.com/embed/", content)
            self.assertNotIn("SUPABASE_SECRET_KEY", content)
            self.assertTrue(path.with_name("review-data.json").exists())
