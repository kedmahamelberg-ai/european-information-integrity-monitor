"""Regression checks for government review publication and source binding."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from government_reviews import apply_confirmed_corrections, source_fingerprint, source_evidence_fingerprint, source_identity_fingerprint
from collect_government_news import ROLE_ENTITY_CODES, article_text, canada_release_date
from repair_government_full_speech import full_speech_text


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

    def test_source_reviewed_date_is_idempotent_and_source_bound(self):
        before = source_evidence_fingerprint(self.item)
        updated = dict(self.item, published_at="2026-10-14T00:00:00Z")
        correction = {
            "id": "source-1", "review_origin": "source_reviewed_agent",
            "source_evidence_fingerprint": before,
            "source_evidence_fingerprint_after": source_evidence_fingerprint(updated),
            "published_at": updated["published_at"], "published_date": "2026-10-14",
        }
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]), (["source-1"], []))
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]), (["source-1"], []))
        self.assertEqual(self.item["published_date"], "2026-10-14")
        self.assertFalse(self.item["human_reviewed"])
        self.item["title"] = "A different source"
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]), ([], ["source-1"]))

    def test_full_source_repair_keeps_review_bound_to_archive_identity(self):
        original = source_evidence_fingerprint(self.item)
        correction = {
            "id": "source-1", "review_origin": "source_reviewed_agent",
            "source_evidence_fingerprint": original,
            "source_identity_fingerprint": source_identity_fingerprint(self.item),
            "full_source_url": "https://example.test/full",
            "relevance": "related", "topics": ["artificial_intelligence"],
        }
        self.item.update(full_source_url="https://example.test/full",
                         source_text_chars=7200, source_text_sha256="verified")
        self.assertEqual(apply_confirmed_corrections([self.item], [correction]), (["source-1"], []))
        self.assertEqual(self.item["topics"], ["artificial_intelligence"])

    def test_canada_visible_dateline_and_page_details_override_issued_metadata(self):
        page = ('<meta name="dcterms.issued" content="2026-10-29">'
                '<div class="news-release-container"><p>October 27, 2026 - Edmundston - ACOA</p>'
                '<p>' + 'This is a full official article body. ' * 5 + '</p></div>'
                '<time property="dateModified">2026-10-27</time>')
        with patch("collect_government_news.fetch", return_value=("https://example.test", page.encode())):
            self.assertEqual(canada_release_date("https://example.test").isoformat(), "2026-10-27")

    def test_canada_conflicting_unconfirmed_dates_require_review(self):
        page = ('<meta name="dcterms.issued" content="2026-10-29">'
                '<div class="news-release-container"><p>October 27, 2026 - Edmundston - ACOA</p>'
                '<p>' + 'This is a full official article body. ' * 5 + '</p></div>')
        with patch("collect_government_news.fetch", return_value=("https://example.test", page.encode())):
            with self.assertRaisesRegex(RuntimeError, "source review required"):
                canada_release_date("https://example.test")

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

    def test_china_attachment_notice_is_not_classified_as_full_article(self):
        page = ('<div class="Artical_Content"><p>BEIJING, Oct. 18 -- The premier spoke at the conference.</p>'
                '<p>Please see the attachment for the English version of the full text of the address.</p></div>')
        with patch("collect_government_news.fetch", return_value=("https://english.www.gov.cn/news/202610/18/content_WS6ad4d9c8c6d00ca5f9a0dc44.html", page.encode())):
            with self.assertRaisesRegex(RuntimeError, "attachment notice"):
                article_text({"country_code": "CN", "url": "https://english.www.gov.cn/news/202610/18/content_WS6ad4d9c8c6d00ca5f9a0dc44.html"})

    def test_croatian_article_includes_intro_before_materials_link(self):
        page = ('<p class="article-intro">The cabinet approved changes to the bill.</p>'
                '<div class="article-content">Meeting materials are available via this link.</div>')
        with patch("collect_government_news.fetch", return_value=("https://example.test", page.encode())):
            article = article_text({"country_code": "HR", "url": "https://example.test"})
        self.assertEqual(article, "The cabinet approved changes to the bill. Meeting materials are available via this link.")


if __name__ == "__main__":
    unittest.main()
