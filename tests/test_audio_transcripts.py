import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eiim.audio_transcripts import AudioTranscripts, assess_segments, english_result, speech_coverage, transcribe_audio_file
from eiim.hybrid import retrieve_retained_captions
from eiim.language_access import caption_state, EnglishCaptionAccess, access_records, usable_english_transcript
from eiim.reclassification import evidence_input
from eiim.storage import MemoryStore, record

VIDEO = {"video_id": "abcDEFG1234", "original_audio_language": "de"}
TEXT = "The parliament debated a new energy agreement with neighbouring countries and discussed how households would be protected during winter if supplies were interrupted."
SPEECH = {"language": "de", "language_probability": .95, "duration": 20,
          "segments": [{"text": TEXT, "start": 1, "end": 19}], "discarded_segments": 0,
          "task": "translate", "output_language": "en", "model": "small",
          "audio_complete": True, "speech_coverage": {"complete": True,"speech_seconds":18}}


class AudioTests(unittest.TestCase):
    def test_complete_short_speech_is_valid_without_twenty_words(self):
        speech = dict(SPEECH, duration=4, speech_coverage={"complete":True,"speech_seconds":4},
                      segments=[{"text":"We demand fair elections.","start":0,"end":4}])
        self.assertTrue(usable_english_transcript(english_result(VIDEO, speech)))

    def test_few_words_cannot_stand_in_for_a_long_speech(self):
        speech=dict(SPEECH,duration=100,speech_coverage={"complete":True,"speech_seconds":100},
                    segments=[{"text":"We demand fair elections.","start":0,"end":100}])
        self.assertFalse(english_result(VIDEO,speech)["eligible"])

    def test_silence_does_not_turn_complete_short_speech_into_missing_evidence(self):
        raw = [dict(text="We demand fair elections.", start=1., end=4., avg_logprob=-.2,
                    no_speech_prob=.9, compression_ratio=1.),
               dict(text="Thank you.", start=8., end=10., avg_logprob=-2.,
                    no_speech_prob=.99, compression_ratio=1.)]
        assessed = assess_segments(raw, [{"start":1., "end":4.}])
        self.assertEqual(assessed["discarded_segments"], 0)
        self.assertEqual(assessed["ignored_non_speech_segments"], 1)
        self.assertTrue(usable_english_transcript(english_result(VIDEO, dict(SPEECH, **assessed))))

    def test_low_confidence_speech_cannot_be_relabelled_as_silence(self):
        raw = [dict(text="A disputed sentence.", start=1., end=4., avg_logprob=-1.1,
                    no_speech_prob=.9, compression_ratio=1.)]
        assessed = assess_segments(raw, [{"start":1.,"end":4.}])
        self.assertEqual(assessed["discarded_segments"], 1)
        self.assertFalse(assessed["speech_coverage"]["complete"])

    def test_confident_quiet_boundary_words_are_retained(self):
        raw = [dict(text="Thank you.",start=0.,end=.2,avg_logprob=-.2,no_speech_prob=.1,compression_ratio=1.),
               dict(text=TEXT,start=1.,end=19.,avg_logprob=-.2,no_speech_prob=.1,compression_ratio=1.)]
        assessed=assess_segments(raw,[{"start":1.,"end":19.}])
        self.assertEqual(len(assessed["segments"]),2)
        self.assertEqual(assessed["ignored_non_speech_segments"],0)

    def test_untranscribed_beginning_middle_or_end_blocks_full_evidence(self):
        region = [{"start":0.,"end":20.}]
        for spans in [[(2,20)], [(0,9),(11,20)], [(0,18)]]:
            segments=[{"start":a,"end":b,"text":TEXT} for a,b in spans]
            coverage=speech_coverage(region,segments)
            self.assertFalse(coverage["complete"])
            result=english_result(VIDEO,dict(SPEECH,segments=segments,speech_coverage=coverage))
            self.assertFalse(result["eligible"])
            self.assertFalse(result["transcript_complete"])

    def test_full_audio_and_explicit_english_translation_are_required(self):
        for changed in [dict(audio_complete=False), dict(audio_complete=None),
                        dict(speech_coverage={}), dict(output_language="de"), dict(task="transcribe")]:
            self.assertFalse(english_result(VIDEO,dict(SPEECH,**changed))["eligible"])

    def test_timestamps_past_actual_audio_end_are_invalid(self):
        result=english_result(VIDEO,dict(SPEECH,segments=[{"text":TEXT,"start":1,"end":24}]))
        self.assertEqual(result["failure_reason"],"AudioInvalidSegments")

    def test_only_timestamp_precision_is_tolerated_in_speech_coverage(self):
        self.assertTrue(speech_coverage([{"start":0.,"end":4.}], [{"start":.2,"end":3.8}])["complete"])
        self.assertFalse(speech_coverage([{"start":0.,"end":4.}], [{"start":.6,"end":3.8}])["complete"])

    def test_repetition_and_nonfinite_confidence_are_not_usable(self):
        raw=dict(text=TEXT,start=1.,end=19.,avg_logprob=-.2,no_speech_prob=.1,compression_ratio=3.)
        self.assertEqual(assess_segments([raw],[{"start":1.,"end":19.}])["discarded_segments"],1)
        with self.assertRaises(ValueError):
            assess_segments([dict(raw,avg_logprob=float('nan'))],[{"start":1.,"end":19.}])

    def test_provenance_names_the_model_actually_used(self):
        self.assertEqual(english_result(VIDEO,dict(SPEECH,model="medium"))["transcription_model"],"medium")

    def test_partial_worker_result_is_never_counted_as_saved(self):
        def partial(command, **kwargs):
            Path(command[-1],"result.json").write_text(json.dumps(dict(SPEECH,discarded_segments=1)))
            return SimpleNamespace(returncode=0)
        audio=AudioTranscripts(runner=partial)
        self.assertFalse(audio.check(VIDEO)["eligible"])
        self.assertEqual(audio.saved,0)

    def test_single_full_audio_translation_and_decode_failure_is_closed(self):
        segment=dict(text="We demand fair elections.",start=0.,end=4.,avg_logprob=-.2,
                     no_speech_prob=.1,compression_ratio=1.)
        calls=[]
        loaded=[]
        def transcribe(waveform,**kwargs):
            calls.append(kwargs)
            return iter([segment]),SimpleNamespace(language="en",language_probability=.95)
        modules={
            "faster_whisper": SimpleNamespace(WhisperModel=lambda name,**k:(loaded.append(name) or SimpleNamespace(transcribe=transcribe))),
            "faster_whisper.audio": SimpleNamespace(decode_audio=lambda *a,**k:[0]*64000),
            "faster_whisper.vad": SimpleNamespace(VadOptions=lambda **k:k,
                get_speech_timestamps=lambda *a,**k:[{"start":0,"end":64000}]),
        }
        with patch.dict(sys.modules,modules):
            speech=transcribe_audio_file("private-audio",4)
            self.assertTrue(english_result(VIDEO,speech)["eligible"])
            self.assertEqual(len(calls),1)
            self.assertEqual(loaded,["medium"])
            self.assertEqual(calls[0]["task"],"translate")
            truncated=transcribe_audio_file("private-audio",20,model_name="medium")
            self.assertFalse(english_result(VIDEO,truncated)["eligible"])
            def broken():
                yield segment
                raise ValueError("decoder failed after the first segment")
            modules["faster_whisper"].WhisperModel=lambda *a,**k:SimpleNamespace(
                transcribe=lambda *a,**k:(broken(),SimpleNamespace(language="en",language_probability=.95)))
            failed=transcribe_audio_file("private-audio",4,model_name="medium")
            self.assertEqual(failed["failure_reason"],"AudioTranscriptionFailed")
            self.assertNotIn("segments",failed)
            modules["faster_whisper"].WhisperModel=lambda *a,**k:SimpleNamespace(
                transcribe=lambda *a,**k:(broken(),SimpleNamespace(language="en",language_probability=.2)))
            uncertain=transcribe_audio_file("private-audio",4,model_name="medium")
            self.assertEqual(uncertain["failure_reason"],"AudioLanguageUncertain")
            self.assertNotIn("segments",uncertain)

    def test_later_network_failure_cannot_erase_saved_evidence(self):
        saved = english_result(VIDEO, SPEECH)
        failure = dict(saved, eligible=False, transcript_english=[], checked_at="9999-01-01", failure_reason="IpBlocked")
        rows = [record("pipeline_runs", "b", "one", saved)["record"],
                record("pipeline_runs", "b", "two", failure)["record"]]
        result = access_records(rows)[("b", VIDEO["video_id"])]
        self.assertEqual(caption_state(result), "saved")

    def test_translation_provenance_and_missing_material_reach_classifier(self):
        result = english_result(VIDEO, dict(SPEECH, discarded_segments=1))
        self.assertEqual(caption_state(result), "incomplete")
        self.assertFalse(usable_english_transcript(result))
        self.assertEqual(result["failure_reason"], "AudioIncompleteTranscript")
        self.assertEqual(result["original_language"], "de")
        self.assertEqual(result["caption_translation"], "whisper_translation")
        self.assertEqual(result["transcript_english"][0]["duration"], 18)
        self.assertTrue(evidence_input(VIDEO, result)["transcript_truncated"])

    def test_quarantined_access_hash_is_not_usable(self):
        saved = english_result(VIDEO, SPEECH)
        row = record("pipeline_runs", "b", "quarantined", saved)["record"]
        row["payload_hash"] = "7f4757c6b7c321d8773c2648205489d7a72abccb4500f7369a2f582fc0d84d65"
        access = access_records([row])[("b", VIDEO["video_id"])]
        self.assertEqual(caption_state(access), "incomplete")
        self.assertFalse(usable_english_transcript(access))

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

    def test_unavailable_video_does_not_block_following_sources(self):
        def unavailable(command, **kwargs):
            Path(command[-1], "result.json").write_text(json.dumps({
                "failure_reason": "AudioDownloadUnavailable",
                "audio_download_error": "video_unavailable",
            }))
            return SimpleNamespace(returncode=0)
        audio = AudioTranscripts(runner=unavailable)
        for _ in range(3):
            self.assertEqual(audio.check(VIDEO)["failure_reason"], "AudioDownloadUnavailable")
        self.assertIsNone(audio.stopped)
        self.assertEqual(audio.attempted, 3)
        self.assertEqual(audio.download_errors["video_unavailable"], 3)

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
