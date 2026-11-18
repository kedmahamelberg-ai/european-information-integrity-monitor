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
from audit_government_sources import audit_fingerprint, audit_one, select_batch


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

    def test_canada_source_date_conflict_is_recorded(self):
        with patch("audit_government_sources.article_text",
                   return_value="A full official article. " * 10), \
             patch("audit_government_sources.canada_release_date",
                   return_value=dt.date(2026, 10, 27)), \
             patch("audit_government_sources.audit_model", return_value=[]):
            issues = audit_one(self.item)
        self.assertTrue(any(issue["field"] == "published_at" for issue in issues))

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

