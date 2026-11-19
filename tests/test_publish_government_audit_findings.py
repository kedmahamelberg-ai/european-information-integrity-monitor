"""A completed audit publishes candidate evidence without a false workflow failure."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish_government_audit_findings as publish


class PublishAuditFindingsTests(unittest.TestCase):
    def test_issue_body_contains_exact_field_source_and_evidence(self):
        body = publish.issue_body({"item-1": {"country_code": "CN",
            "source_url": "https://english.www.gov.cn/example.html",
            "status": "candidate_requires_source_review",
            "issues": [{"field": "ticker_message", "kind": "editorial",
                        "evidence": "The article proposes wider AI use.",
                        "explanation": "The ticker calls this AI cooperation."}]}})
        self.assertIn("item-1", body)
        self.assertIn("https://english.www.gov.cn/example.html", body)
        self.assertIn("**ticker_message** (editorial)", body)
        self.assertIn("The article proposes wider AI use.", body)

    def test_existing_unchanged_issue_is_not_reposted(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            summary = Path(directory) / "summary.md"
            findings = {"item-1": {"country_code": "CN",
                "source_url": "https://english.www.gov.cn/example.html",
                "status": "source_unverified", "issues": [{
                    "field": "full_source", "kind": "source_extraction",
                    "evidence": "HTTP 403", "explanation": "Source blocked."}]}}
            report.write_text(json.dumps({"checked_total": 57,
                "newly_attempted_ids": [], "open_candidate_findings": findings}))
            issue = {"number": 17, "html_url": "https://github.com/example/issues/17",
                     "body": publish.issue_body(findings)}
            with patch.object(publish, "REPORT", report), \
                 patch.object(publish, "find_existing_issue", return_value=issue), \
                 patch.object(publish, "github") as github, \
                 patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo",
                     "GITHUB_RUN_ID": "123", "GITHUB_STEP_SUMMARY": str(summary)}):
                publish.main()
            github.assert_not_called()
            self.assertIn("Checked IDs: 57", summary.read_text())
            self.assertIn("https://github.com/example/issues/17", summary.read_text())


if __name__ == "__main__":
    unittest.main()
