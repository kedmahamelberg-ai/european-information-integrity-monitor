import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eiim.audio_transcripts import AudioTranscripts, english_result
from eiim.hybrid import retrieve_retained_captions
from eiim.language_access import caption_state, EnglishCaptionAccess, access_records
from eiim.reclassification import evidence_input
from eiim.storage import MemoryStore, record

VIDEO = {"video_id": "abcDEFG1234", "original_audio_language": "de"}
TEXT = "The parliament debated a new energy agreement with neighbouring countries and discussed how households would be protected during winter if supplies were interrupted."
SPEECH = {"language": "de", "language_probability": .95, "duration": 20,
          "segments": [{"text": TEXT, "start": 1, "end": 19}], "discarded_segments": 0}


class AudioTests(unittest.TestCase):
    def test_later_network_failure_cannot_erase_saved_evidence(self):
        saved = english_result(VIDEO, SPEECH)
        failure = dict(saved, eligible=False, transcript_english=[], checked_at="9999-01-01", failure_reason="IpBlocked")
        rows = [record("pipeline_runs", "b", "one", saved)["record"],
                record("pipeline_runs", "b", "two", failure)["record"]]
        result = access_records(rows)[("b", VIDEO["video_id"])]
        self.assertEqual(caption_state(result), "saved")

    def test_translation_provenance_and_missing_material_reach_classifier(self):
        result = english_result(VIDEO, dict(SPEECH, discarded_segments=1))
        self.assertEqual(caption_state(result), "saved")
        self.assertEqual(result["original_language"], "de")
        self.assertEqual(result["caption_translation"], "whisper_translation")
        self.assertEqual(result["transcript_english"][0]["duration"], 18)
        self.assertTrue(evidence_input(VIDEO, result)["transcript_truncated"])

    def test_empty_uncertain_invalid_and_repetitive_speech_stays_unclassified(self):
        for speech in [dict(SPEECH, segments=[]), dict(SPEECH, language_probability=.2),
                       dict(SPEECH, language="und"),
                       dict(SPEECH, segments=[{"text":TEXT,"start":-1,"end":19}]),
                       dict(SPEECH, segments=[{"text":"thank you "*30,"start":0,"end":19}])]:
            result = english_result(VIDEO, speech)
            self.assertFalse(result["eligible"])
            self.assertFalse(result["transcript_english"])

    def test_worker_bounds_cleans_audio_and_stops_on_repeated_access_failures(self):
        folders = []
        def blocked(command, **kwargs):
            folder = Path(command[-1]); folders.append(folder)
            (folder / "audio.webm").write_bytes(b"temporary audio")
            (folder / "result.json").write_text(json.dumps({"failure_reason":"AudioAccessBlocked"}))
            self.assertEqual(kwargs["timeout"], 900)
            return SimpleNamespace(returncode=0)
        audio = AudioTranscripts(runner=blocked)
        for _ in range(3): audio.check(VIDEO)
        self.assertEqual(audio.stopped, "audio_access_unavailable")
        self.assertIsNone(audio.check(VIDEO))
        self.assertTrue(all(not p.exists() for p in folders))

    def test_timeout_and_run_limit_never_admit_evidence(self):
        def timeout(*args, **kwargs): raise subprocess.TimeoutExpired("worker", 900)
        audio = AudioTranscripts(max_videos=1, runner=timeout)
        result = audio.check(VIDEO)
        self.assertEqual(result["failure_reason"], "AudioTimedOut")
        self.assertFalse(result["eligible"])
        self.assertIsNone(audio.check(VIDEO))
        self.assertEqual(audio.stopped, "audio_run_limit")

    def test_blocked_captions_recover_and_restart_does_not_repeat_saved_audio(self):
        store = MemoryStore()
        for vid in ["abcDEFG1234", "abcDEFG5678"]:
            store.write("b", [record("candidate_videos", "b", "c:"+vid, dict(VIDEO,video_id=vid), vid),
                              record("sampled_videos", "b", "s:"+vid, {"selected_for_sample":True}, vid)])
        def success(command, **kwargs):
            Path(command[-1], "result.json").write_text(json.dumps(SPEECH))
            return SimpleNamespace(returncode=0)
        class Blocked:
            blocked = "RequestBlocked"
            def check(self, *args, **kw):
                return {"failure_reason":"RequestBlocked", "transcript_english":[]}
        with patch("eiim.language_access.EnglishCaptionAccess", Blocked), patch("eiim.caption_provider.SupadataCaptions.from_environment", return_value=None):
            audio = AudioTranscripts(runner=success)
            report = retrieve_retained_captions(store, "b", audio)
            self.assertEqual(report["coverage"]["saved_transcripts"], 2)
            report = retrieve_retained_captions(store, "b", audio)
            self.assertEqual(report["attempted_videos"], 0)
            self.assertEqual(audio.attempted, 2)

    def test_bad_translation_track_cannot_prevent_valid_english_track(self):
        from test_language_access import Track
        class BadTranslation(Track):
            def translate(self, language): raise ValueError("track broken")
        reader = EnglishCaptionAccess(SimpleNamespace(list=lambda _: [BadTranslation("de",translatable=True),Track("en")]))
        self.assertEqual(caption_state(reader.check(VIDEO)), "saved")

    def test_unattempted_sources_take_priority_over_failed_sources(self):
        store = MemoryStore()
        for vid in ["abcDEFG1234", "abcDEFG5678"]:
            store.write("b", [record("candidate_videos", "b", "c:"+vid, dict(VIDEO,video_id=vid), vid),
                              record("sampled_videos", "b", "s:"+vid, {"selected_for_sample":True}, vid)])
        old = english_result(VIDEO, dict(SPEECH, segments=[]))
        old["audio_attempted_at"] = "2026-01-01T00:00:00+00:00"
        store.write("b", [record("pipeline_runs", "b", "old", old, VIDEO["video_id"])])
        attempted = []
        def success(command, **kwargs):
            attempted.append(command[-2])
            Path(command[-1], "result.json").write_text(json.dumps(SPEECH))
            return SimpleNamespace(returncode=0)
        class Blocked:
            blocked = "RequestBlocked"
            def check(self, *args, **kw): return {"failure_reason":"RequestBlocked"}
        with patch("eiim.language_access.EnglishCaptionAccess", Blocked), patch("eiim.caption_provider.SupadataCaptions.from_environment", return_value=None):
            retrieve_retained_captions(store, "b", AudioTranscripts(max_videos=1, runner=success))
        self.assertEqual(attempted, ["abcDEFG5678"])

    def test_failed_track_continues_to_next_available_track(self):
        from test_language_access import Track
        class BadTrack(Track):
            def fetch(self): raise ValueError("track broken")
        reader = EnglishCaptionAccess(SimpleNamespace(list=lambda _: [BadTrack("en"),Track("en",generated=True)]))
        self.assertEqual(caption_state(reader.check(VIDEO)), "saved")
