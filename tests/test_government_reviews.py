"""Regression checks for government review publication and source binding."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from government_reviews import apply_confirmed_corrections, source_fingerprint, source_evidence_fingerprint
from collect_government_news import ROLE_ENTITY_CODES, article_text


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

    def test_confirmed_review_can_correct_a_misleading_summary(self):
        correction = {
            "id": "source-1", "source_fingerprint": source_fingerprint(self.item),
            "english_summary": "A proposal to improve ambulance staff safety.",
        }
        applied, stale = apply_confirmed_corrections([self.item], [correction])
        self.assertEqual((applied, stale), (["source-1"], []))
        self.assertEqual(self.item["english_summary"], correction["english_summary"])

    def test_label_changes_do_not_invalidate_source_fingerprint(self):
        original = source_fingerprint(self.item)
        self.item["topics"] = ["health_biosecurity"]
        self.assertEqual(source_fingerprint(self.item), original)

    def test_agent_source_review_preserves_provisional_status_and_copy_binding(self):
        correction = {
            "id": "source-1", "review_origin": "source_reviewed_agent",
            "source_evidence_fingerprint": source_evidence_fingerprint(self.item),
            "topics": [], "english_summary": "A corrected source-based summary.",
        }
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]),
                         (["source-1"], []))
        self.assertEqual(self.item["classification_status"], "provisional")
        self.assertFalse(self.item["human_reviewed"])
        self.assertTrue(self.item["source_reviewed"])
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]),
                         (["source-1"], []))

    def test_future_roles_require_coded_entity(self):
        self.assertIn("SWE", ROLE_ENTITY_CODES)
        self.assertIn("EU", ROLE_ENTITY_CODES)
        self.assertNotIn("", ROLE_ENTITY_CODES)

    def test_source_review_withholds_attachment_stub_from_publication(self):
        correction = {
            "id": "source-1", "review_origin": "source_reviewed_agent",
            "source_evidence_fingerprint": source_evidence_fingerprint(self.item),
            "withhold_reason": "full_source_unavailable",
        }
        self.item.update(english_summary="The article is attached.",
                         ticker_message="No text was provided to classify.")
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]),
                         (["source-1"], []))
        self.assertEqual(self.item["classification_status"], "source_incomplete")
        self.assertFalse(self.item["related"])
        self.assertNotIn("english_summary", self.item)
        self.assertNotIn("ticker_message", self.item)
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]),
                         (["source-1"], []))

    def test_german_attachment_notice_is_not_classified_as_full_article(self):
        page = ('<div id="rs_reading_area_content"><div class="bpa-richtext">'
                '<p>Die Pressemitteilung finden Sie im Anhang.</p></div></div>')
        with patch("collect_government_news.fetch", return_value=("https://example.test", page.encode())):
            with self.assertRaisesRegex(RuntimeError, "attachment notice"):
                article_text({"country_code": "DE", "url": "https://example.test"})

    def test_croatian_article_includes_intro_before_materials_link(self):
        page = ('<p class="article-intro">The cabinet approved changes to the bill.</p>'
                '<div class="article-content">Meeting materials are available via this link.</div>')
        with patch("collect_government_news.fetch", return_value=("https://example.test", page.encode())):
            article = article_text({"country_code": "HR", "url": "https://example.test"})
        self.assertEqual(article, "The cabinet approved changes to the bill. Meeting materials are available via this link.")


if __name__ == "__main__":
    unittest.main()
