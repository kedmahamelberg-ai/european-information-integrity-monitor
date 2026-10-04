import unittest
from datetime import datetime, timezone
from eiim.model_policy import resolve_policy
from eiim.core import config


class ModelPolicyTests(unittest.TestCase):
    def test_exact_cutover_and_rates(self):
        before = resolve_policy(datetime(2026, 12, 9, 23, 59, 59, tzinfo=timezone.utc))
        after = resolve_policy(datetime(2026, 12, 10, tzinfo=timezone.utc))
        self.assertEqual(before["model"], "gpt-5-nano")
        self.assertEqual(after["model"], "gpt-5.6-luna")
        self.assertEqual(before["reasoning_effort"], "low")
        self.assertEqual(after["reasoning_effort"], "low")
        self.assertEqual(before["output_usd_per_million"], 0.40)
        self.assertEqual(after["input_usd_per_million"], 0.25)
        self.assertEqual(config("models")["weekly_usd_ceiling"], 5)
        self.assertNotIn("temperature", before)
        self.assertNotIn("temperature", after)

    def test_naive_date_rejected(self):
        with self.assertRaises(ValueError):
            resolve_policy(datetime(2026, 12, 10))
