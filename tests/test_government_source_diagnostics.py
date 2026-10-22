import importlib.util
from pathlib import Path
import socket
import sys
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location(
    "collect_government_news", Path(__file__).resolve().parents[1] / "scripts/collect_government_news.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class GovernmentSourceDiagnosticsTests(unittest.TestCase):
    def test_http_denial_and_server_failure_remain_uncertain(self):
        for code, expected in [(403, "possible_access_restriction"),
                               (429, "possible_access_restriction"),
                               (503, "possible_service_outage")]:
            with self.subTest(code=code):
                error = urllib.error.HTTPError("https://example.gov/news", code, "test", {}, None)
                result = collector.source_failure_diagnostic(error)
                self.assertEqual(result["http_status"], code)
                self.assertEqual(result["error_category"], expected)
                self.assertTrue(result["needs_independent_check"])

    def test_timeout_is_not_reported_as_a_takedown(self):
        result = collector.source_failure_diagnostic(urllib.error.URLError(socket.timeout()))
        self.assertEqual(result["error_category"], "timeout_or_network_path")

    def test_successful_fetch_with_broken_page_format_needs_collector_review(self):
        result = collector.source_failure_diagnostic(RuntimeError("News card has no publication date"))
        self.assertEqual(result["error_category"], "collector_or_page_format_changed")


if __name__ == "__main__":
    unittest.main()
