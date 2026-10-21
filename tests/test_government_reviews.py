"""Regression checks for government review publication and source binding."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from government_reviews import apply_confirmed_corrections, source_fingerprint
from collect_government_news import ROLE_ENTITY_CODES


class GovernmentReviewTests(unittest.TestCase):
    def setUp(self):
        self.item = {
            "id": "source-1", "url": "https://example.test/article",
            "title": "Ambulance safety", "published_at": "2026-10-15T00:00:00Z",
            "english_summary": "Ambulance staff safety proposal.",
            "source_text_chars": 800, "translated_text_chars": 760,
            "relevance": "related", "topics": ["civil_protection"],
            "roles": [], "classification_status": "provisional",
        }

    def test_confirmed_review_overrides_ai_on_public_checkpoint(self):
        correction = {
            "id": "source-1", "source_fingerprint": source_fingerprint(self.item),
            "relevance": "not_related", "topics": [], "roles": [],
            "ticker_message": "A confirmed human message.",
        }
        applied, stale = apply_confirmed_corrections([self.item], [correction])
        self.assertEqual((applied, stale), (["source-1"], []))
        self.assertFalse(self.item["related"])
        self.assertEqual(self.item["primary_narrative"], "none_unclear")
        self.assertEqual(self.item["classification_status"], "human_reviewed")
        self.assertTrue(self.item["human_reviewed"])
        self.assertEqual(self.item["ticker_message"], "A confirmed human message.")

    def test_changed_source_does_not_receive_stale_review(self):
        correction = {
            "id": "source-1", "source_fingerprint": source_fingerprint(self.item),
            "relevance": "not_related", "topics": [], "roles": [],
        }
        self.item["english_summary"] = "Updated source content."
        applied, stale = apply_confirmed_corrections([self.item], [correction])
        self.assertEqual((applied, stale), ([], ["source-1"]))
        self.assertEqual(self.item["classification_status"], "provisional")

    def test_label_changes_do_not_invalidate_source_fingerprint(self):
        original = source_fingerprint(self.item)
        self.item["topics"] = ["health_biosecurity"]
        self.assertEqual(source_fingerprint(self.item), original)

    def test_future_roles_require_coded_entity(self):
        self.assertIn("SWE", ROLE_ENTITY_CODES)
        self.assertIn("EU", ROLE_ENTITY_CODES)
        self.assertNotIn("", ROLE_ENTITY_CODES)


if __name__ == "__main__":
    unittest.main()
