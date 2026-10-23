import datetime as dt
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("government_schedule", Path(__file__).resolve().parents[1] / "scripts/government_schedule.py")
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)


class GovernmentScheduleTests(unittest.TestCase):
    def test_tomorrow_warmup_waits_until_1500_amsterdam(self):
        plan = schedule.schedule_plan(dt.datetime.fromisoformat("2026-10-19T12:47:00+00:00"), "schedule")
        self.assertEqual(plan["enabled"], "true")
        self.assertEqual(plan["wait_seconds"], 780)
        self.assertEqual(plan["until"], "2026-10-19T15:00:00+02:00")

    def test_winter_and_dst_dates_keep_local_1500(self):
        for day, offset, utc_hour in [("2026-10-24", "+02:00", 12), ("2026-10-25", "+01:00", 13), ("2027-03-28", "+02:00", 12)]:
            plan = schedule.schedule_plan(dt.datetime.fromisoformat(f"{day}T{utc_hour}:47:00+00:00"), "schedule")
            self.assertEqual(plan["until"], f"{day}T15:00:00{offset}")
            self.assertEqual(plan["wait_seconds"], 780)

    def test_delayed_attempt_keeps_daily_cutoff(self):
        plan = schedule.schedule_plan(dt.datetime.fromisoformat("2026-10-19T16:07:00+00:00"), "schedule")
        self.assertEqual(plan["wait_seconds"], 0)
        self.assertEqual(plan["until"], "2026-10-19T15:00:00+02:00")

    def test_manual_backfills_are_not_delayed_or_bounded(self):
        plan = schedule.schedule_plan(dt.datetime.fromisoformat("2026-10-19T08:00:00+00:00"), "workflow_dispatch")
        self.assertEqual(plan, {"enabled": "true", "until": "", "wait_seconds": 0})

    def test_unexpected_early_schedule_is_skipped(self):
        plan = schedule.schedule_plan(dt.datetime.fromisoformat("2026-10-19T05:00:00+00:00"), "schedule")
        self.assertEqual(plan["enabled"], "false")

    def test_completed_daily_sources_only_retry_saved_classifications(self):
        state = {"source_cursors": {"NL": "2026-10-19T13:00:00+00:00", "DE": "2026-10-19T13:15:00+00:00"}}
        self.assertEqual(schedule.collection_mode(state, {"NL", "DE"}, "2026-10-19T15:00:00+02:00"), "classify-only")

    def test_partial_or_stale_sources_are_retried(self):
        for cursor in [None, "bad", "2026-10-18T13:00:00+00:00", "2026-10-19T13:00:00"]:
            state = {"source_cursors": {"NL": "2026-10-19T13:00:00+00:00", "DE": cursor}}
            self.assertEqual(schedule.collection_mode(state, {"NL", "DE"}, "2026-10-19T15:00:00+02:00"), "collect")

    def test_empty_allowlist_never_counts_as_completed(self):
        self.assertEqual(schedule.collection_mode({}, set(), "2026-10-19T15:00:00+02:00"), "collect")

    def test_afternoon_checks_every_ready_source_after_morning_pass(self):
        state = {"source_cursors": {
            "NL": "2026-10-22T07:00:00+00:00",
            "DE": "2026-10-21T13:00:00+00:00",
            "BE": "2026-10-22T07:00:00+00:00",
        }}
        self.assertEqual(schedule.daily_plan(state, {"NL", "DE", "BE"}, "retry",
                                             "2026-10-22T15:00:00+02:00"),
                         {"mode": "collect"})

    def test_afternoon_checks_sources_when_morning_checkpoints_are_complete(self):
        state = {"source_cursors": {"NL": "2026-10-22T07:00:00+00:00",
                                    "DE": "2026-10-22T07:00:00+00:00"}}
        self.assertEqual(schedule.daily_plan(state, {"NL", "DE"}, "retry",
                                             "2026-10-22T15:00:00+02:00"),
                         {"mode": "collect"})

    def test_missing_early_checkpoint_still_checks_every_source(self):
        state = {"source_cursors": {"NL": "2026-10-21T13:00:00+00:00"}}
        self.assertEqual(schedule.daily_plan(state, {"NL", "DE"}, "retry",
                                             "2026-10-22T15:00:00+02:00"),
                         {"mode": "collect"})

    def test_winter_afternoon_also_checks_every_source(self):
        state = {"source_cursors": {"NL": "2026-10-24T22:30:00+00:00",
                                    "DE": "2026-10-24T21:30:00+00:00"}}
        self.assertEqual(schedule.daily_plan(state, {"NL", "DE"}, "retry",
                                             "2026-10-25T15:00:00+01:00"),
                         {"mode": "collect"})

    def test_manual_run_does_not_skip_sources(self):
        state = {"source_cursors": {"NL": "2026-10-22T07:00:00+00:00"}}
        self.assertEqual(schedule.daily_plan(state, {"NL"}, "",
                                             "2026-10-22T15:00:00+02:00"),
                         {"mode": "collect"})

    def test_pending_countries_are_not_enabled(self):
        root = Path(__file__).resolve().parents[1]
        codes = schedule.ready_codes(root / "scripts/collect_government_news.py")
        self.assertEqual(len(codes), 40)
        self.assertIn("MT", codes)
        self.assertFalse(codes & {"AL","CY","FI","FR","IE","LV","LT","NO","RO","RU","UA"})
