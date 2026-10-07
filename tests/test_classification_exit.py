"""CLI exit codes distinguish saved-text work from incomplete acquisition."""
import contextlib
import io
import unittest
from unittest.mock import patch

from eiim.hybrid import main
from eiim.storage import MemoryStore, record


class ClassificationExitTests(unittest.TestCase):
    def run_report(self, report, *options):
        store = MemoryStore()
        store.write("2026-W40", [record("sampled_videos", "2026-W40", "sample:v",
            {"selected_for_sample": True}, "v")])
        with (
            patch("sys.argv", ["hybrid", "--batch", "2026-W40", *options]),
            patch("eiim.hybrid.Store", return_value=store),
            patch("eiim.hybrid.reclassify", return_value=report),
            patch("eiim.hybrid.retrieve_retained_captions", return_value={}),
            patch("eiim.audio_transcripts.AudioTranscripts.from_environment", return_value=None),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            try:
                main()
                code = 0
            except SystemExit as error:
                code = error.code
        return code, output.getvalue()

    def test_runs_34_and_35_complete_saved_text_without_hiding_missing_evidence(self):
        for saved in (59, 63):
            report = {"status": "awaiting_transcripts", "classification_status": "complete",
                "eligible_videos": saved, "classified_videos": saved, "failures": [],
                "coverage": {"sampled_videos": 315, "saved_transcripts": saved,
                    "awaiting_transcripts": 315 - saved}}
            with self.subTest(saved=saved):
                code, output = self.run_report(report)
                self.assertEqual(code, 0)
                self.assertIn('"awaiting_transcripts": ' + str(315 - saved), output)
                self.assertIn('"status": "awaiting_transcripts"', output)
                self.assertEqual(self.run_report(report, "--retrieve-captions")[0], 1)

    def test_real_classification_errors_and_budget_exhaustion_still_fail(self):
        for status in ("partial", "pending_budget", None):
            with self.subTest(status=status):
                self.assertEqual(self.run_report({"status": "complete",
                    "classification_status": status, "failures": []})[0], 1)
        self.assertEqual(self.run_report({"status": "complete",
            "classification_status": "complete", "failures": [{"error_type": "ClassificationUnavailable"}]})[0], 1)

    def test_complete_retrieval_succeeds(self):
        self.assertEqual(self.run_report({"status": "complete",
            "classification_status": "complete", "failures": []}, "--retrieve-captions")[0], 0)

    def test_sunday_hands_pending_acquisition_to_mac_but_preserves_real_failures(self):
        for classification, errors, expected in [('complete', [], 0), ('pending_budget', [], 1), ('partial', [{'error_type':'ClassificationUnavailable'}], 1)]:
            report = {'status':'awaiting_transcripts','classification_status':classification,'failures':errors,'coverage':{'awaiting_transcripts':252}}
            with patch('sys.argv', ['hybrid','--collect']), patch('eiim.hybrid.Store', return_value=MemoryStore()), patch('eiim.hybrid.collect_week', return_value=report), contextlib.redirect_stdout(io.StringIO()) as output:
                try:
                    main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            self.assertEqual(code, expected)
            self.assertIn('awaiting_transcripts', output.getvalue())
