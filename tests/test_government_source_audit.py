"""Verify source-audit cursor, date checks and change detection."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_government_sources as audit
from audit_government_sources import (audit_fingerprint, audit_one,
                                      reconcile_findings, select_batch,
                                      supported_issue)


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.item = {"id": "example-id", "country_code": "CA",
                     "url": "https://www.canada.ca/en/example.html",
                     "title": "Official release",
                     "published_at": "2026-10-29T04:00:00+00:00",
                     "published_date": "2026-10-29",
                     "english_summary": "Funding announced.",
                     "ticker_message": "Funding announced.",
                     "relevance": "not_related", "topics": [],
                     "source_text_chars": 100}

    def test_new_published_label_reopens_checked_item(self):
        now = dt.datetime.now(dt.timezone.utc)
        original = audit_fingerprint(self.item)
        self.assertEqual(select_batch([self.item], {
            "example-id": {"fingerprint": original}}, {}, 15, now), [])
        self.item["topics"] = ["artificial_intelligence"]
        self.assertEqual([x["id"] for x in select_batch([self.item], {
            "example-id": {"fingerprint": original}}, {}, 15, now)],
            ["example-id"])

    def test_changed_speaker_or_rationale_reopens_the_source_audit(self):
        original = audit_fingerprint(self.item)
        self.item["viewpoints"] = [{"speaker": "An incorrect person"}]
        self.assertNotEqual(audit_fingerprint(self.item), original)
        issue = {"field": "viewpoints", "kind": "translation",
                 "evidence": "The official article names another person.",
                 "explanation": "The published speaker is mistranslated."}
        self.assertTrue(supported_issue(self.item, issue))
        before = audit_fingerprint(self.item)
        self.item["short_rationale"] = "The rationale contradicts the topic list."
        self.assertNotEqual(audit_fingerprint(self.item), before)

    def test_deferred_failure_does_not_block_other_ids(self):
        now = dt.datetime.now(dt.timezone.utc)
        item2 = dict(self.item, id="example-next", country_code="CN")
        previous = {"example-id": {"fingerprint": audit_fingerprint(self.item),
                    "at": now.isoformat()}}
        self.assertEqual([x["id"] for x in
            select_batch([self.item, item2], {}, previous, 15, now)],
            ["example-next"])

    def test_new_or_changed_publication_precedes_backlog(self):
        now = dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc)
        old = dict(self.item, id="a-old", published_at="2026-10-01T04:00:00+00:00")
        changed = dict(old, id="z-changed", topics=["artificial_intelligence"])
        new = dict(self.item, id="z-new", country_code="HR",
                   published_at="2026-11-18T08:00:00+00:00")
        checked = {"z-changed": {"fingerprint": audit_fingerprint(old)}}
        batch = select_batch([old, new, changed], checked, {}, 3, now,
                             seen_ids={"a-old", "z-changed"})
        self.assertEqual([item["id"] for item in batch],
                         ["z-changed", "z-new", "a-old"])

    def test_pending_record_enters_audit_after_classification(self):
        now = dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc)
        item = dict(self.item, classification_status="pending_classification")
        self.assertEqual(select_batch([item], {}, {}, 15, now), [])
        item["classification_status"] = "provisional"
        self.assertEqual([x["id"] for x in select_batch([item], {}, {}, 15, now)],
                         ["example-id"])

    def test_canada_source_date_conflict_is_recorded(self):
        with patch("audit_government_sources.article_text",
                   return_value="A full official article. " * 10), \
             patch("audit_government_sources.canada_release_date",
                   return_value=dt.date(2026, 10, 27)), \
             patch("audit_government_sources.audit_model", return_value=[]):
            issues = audit_one(self.item)
        self.assertTrue(any(issue["field"] == "published_at" for issue in issues))

    def test_china_archive_local_day_is_not_utc_date_fault(self):
        item = dict(self.item, country_code="CN",
                    url="https://english.www.gov.cn/news/202611/19/content_WSabc.html",
                    published_at="2026-11-18T16:00:00+00:00",
                    published_date="2026-11-19")
        issue = {"field": "published_at", "kind": "date",
                 "evidence": "SHENZHEN, Nov. 19",
                 "explanation": "Saved UTC timestamp is one day earlier."}
        self.assertFalse(supported_issue(item, issue))
        item["published_date"] = "2026-11-18"
        self.assertTrue(supported_issue(item, issue))

    def test_china_portal_heading_overrules_internal_speech_title(self):
        item = dict(self.item, country_code="CN",
                    url="https://english.www.gov.cn/news/202611/19/content_WSabc.html",
                    title="Full text: Remarks at the APEC meeting")
        markup = (b'<meta name="publishdate" content="2026-11-19" />'
                  b'<div class="Artical_Title ">Full text: Remarks at the APEC meeting</div>')
        with patch("audit_government_sources.fetch", return_value=(None, markup)):
            title, day = audit.china_page_metadata(item)
        self.assertEqual(day, "2026-11-19")
        issue = {"field": "title", "kind": "source_extraction",
                 "evidence": "Body speech has a different title.",
                 "explanation": "The saved title omits the internal speech title."}
        self.assertFalse(supported_issue(item, issue, official_title=title))

    def test_no_op_is_removed_but_material_editorial_issue_remains(self):
        no_op = {"field": "title", "kind": "source_extraction",
                 "evidence": "Official heading", "explanation": "The saved title matches the official article."}
        issue = {"field": "ticker_message", "kind": "editorial",
                 "evidence": "The official page describes a draft regulation.",
                 "explanation": "The ticker says the requirements are already set."}
        findings = {"example-id": {"status": "candidate_requires_source_review",
                                   "issues": [no_op, issue]}}
        reconcile_findings(findings, [self.item])
        self.assertEqual(findings["example-id"]["issues"], [issue])

    def test_unsupported_ai_label_is_not_removed_as_no_op(self):
        issue = {"field": "topics", "kind": "label",
                 "evidence": "AI appears only in a list of economic sectors.",
                 "explanation": "The saved AI label is unsupported; this is not a substantive AI action."}
        self.assertTrue(supported_issue(self.item, issue))

    def test_plan_identifies_malta_without_running_model_or_saving_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            output = Path(directory) / "output.txt"
            malta = dict(self.item, country_code="MT")
            with patch.object(audit, "STATE", state), \
                 patch.object(audit, "fetch_snapshot", return_value={
                     "as_of": "2026-11-19T08:00:00+00:00", "items": [malta]}), \
                 patch.object(audit, "audit_one") as review, \
                 patch.object(sys, "argv", ["audit_government_sources.py", "--plan"]), \
                 patch.dict("os.environ", {"GITHUB_OUTPUT": str(output)}):
                audit.main()
            review.assert_not_called()
            self.assertFalse(state.exists())
            self.assertEqual(output.read_text(), "needs_malta=true\n")

    def test_longer_current_source_alone_is_not_an_extraction_fault(self):
        with patch("audit_government_sources.article_text",
                   return_value="A full official article. " * 8), \
             patch("audit_government_sources.canada_release_date",
                   return_value=dt.date(2026, 10, 29)), \
             patch("audit_government_sources.audit_model", return_value=[]):
            self.assertEqual(audit_one(self.item), [])

    def test_saved_cursor_skips_unchanged_item_on_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            report = Path(directory) / "report.json"
            with patch.object(audit, "STATE", state), \
                 patch.object(audit, "REPORT", report), \
                 patch.object(audit, "fetch_snapshot", return_value={
                     "as_of": "2026-11-18T20:00:00+00:00", "items": [self.item]}), \
                 patch.object(audit, "audit_one", return_value=[]) as review, \
                 patch.object(sys, "argv", ["audit_government_sources.py", "--limit", "1"]):
                audit.main()
                audit.main()
            self.assertEqual(review.call_count, 1)
            self.assertEqual(json.loads(state.read_text())["checked"]["example-id"]
                             ["fingerprint"], audit_fingerprint(self.item))
            self.assertEqual(json.loads(state.read_text())["seen_ids"], ["example-id"])


if __name__ == "__main__":
    unittest.main()

