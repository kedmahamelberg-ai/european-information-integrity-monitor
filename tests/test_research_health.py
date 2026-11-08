import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.check_research_health import check, expected_batch


AT = datetime(2026, 11, 8, 22, 45, tzinfo=ZoneInfo("Europe/Amsterdam"))


class ResearchHealthTests(unittest.TestCase):
    def test_completed_week_follows_amsterdam_saturday(self):
        self.assertEqual(expected_batch(AT), "2026-W45")

    def test_empty_new_week_fails_even_with_coded_prior_week(self):
        data = {
            "batches": [{"id": "2026-W44"}, {"id": "2026-W45"}],
            "inventory": [{"batch": "2026-W45", "id": "new"}],
            "videos": [{"batch": "2026-W44", "id": "old", "label": {"topics": []}}],
        }
        with self.assertRaisesRegex(ValueError, "none classified"):
            check(data, AT)

    def test_new_week_with_coded_source_passes(self):
        data = {
            "batches": [{"id": "2026-W45"}],
            "inventory": [{"batch": "2026-W45", "id": "new"}],
            "videos": [{"batch": "2026-W45", "id": "new", "label": {"topics": []}}],
        }
        self.assertIn("1 classified of 1", check(data, AT))

    def test_saved_english_source_without_label_fails(self):
        data = {
            "batches": [{"id": "2026-W45"}],
            "inventory": [
                {"batch": "2026-W45", "id": "coded", "caption_state": "saved"},
                {"batch": "2026-W45", "id": "pending", "caption_state": "saved"},
                {"batch": "2026-W45", "id": "blocked", "caption_state": "blocked"},
            ],
            "videos": [
                {"batch": "2026-W45", "id": "coded", "label": {"topics": []}}
            ],
        }
        with self.assertRaisesRegex(ValueError, "1 of 2 saved-English"):
            check(data, AT)

    def test_missing_week_fails(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            check({"batches": [], "inventory": [], "videos": []}, AT)


if __name__ == "__main__":
    unittest.main()
