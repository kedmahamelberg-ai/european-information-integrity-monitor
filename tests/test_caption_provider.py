import io
import json
import unittest
import urllib.error
from unittest.mock import patch
from eiim.caption_provider import SupadataCaptions
from eiim.storage import MemoryStore, record
from eiim.hybrid import caption_coverage, retrieve_retained_captions, reclassify
import test_hybrid as fixtures

VIDEO = {"video_id": "abcDEFG1234", "original_audio_language": "es"}
RESPONSE = {"lang": "en", "availableLangs": ["en", "es"],
            "content": [{"text": "A public speech", "offset": 1500, "duration": 2500, "lang": "en"}]}

class Response(io.StringIO):
    status = 200

class CaptionProviderTests(unittest.TestCase):
    def provider(self, store=None, response=None, limit=100):
        def opened(request, timeout):
            self.assertIn("mode=native", request.full_url)
            self.assertIn("lang=en", request.full_url)
            self.assertNotIn("private", request.full_url)
            return Response(json.dumps(RESPONSE if response is None else response))
        return SupadataCaptions(store or MemoryStore(), "2026-W40", "test", limit,
                               opener=opened, sleeper=lambda _: None)

    def test_english_saved_with_timestamps_and_original_language(self):
        p = self.provider()
        r = p.check(VIDEO)
        self.assertTrue(r["eligible"])
        self.assertEqual(r["original_language"], "es")
        self.assertEqual(r["transcript_english"][0]["start"], 1.5)
        self.assertEqual(r["caption_retrieval_mode"], "native")

    def test_foreign_fallback_and_invalid_responses_never_admitted(self):
        for data in [dict(RESPONSE, lang="es"), dict(RESPONSE, content=[]),
                     dict(RESPONSE, content="untimed"),
                     dict(RESPONSE, content=[dict(RESPONSE["content"][0], lang="es")]),
                     dict(RESPONSE, content=[dict(RESPONSE["content"][0], offset=-1)])]:
            r = self.provider(response=data).check(VIDEO)
            self.assertFalse(r["eligible"])
            self.assertFalse(r["transcript_english"])

    def test_reservations_survive_restart_and_span_batches(self):
        s = MemoryStore()
        p = self.provider(s, limit=1)
        p.check(VIDEO)
        retry = self.provider(s, limit=1)
        retry.batch = "2026-W41"
        self.assertIsNone(retry.check(VIDEO))
        self.assertIsNone(retry.check(dict(VIDEO, video_id="abcDEFG5678")))
        self.assertEqual(retry.stopped, "monthly_request_limit")
        self.assertEqual(len(s.read("cost_events")), 1)

    def test_quota_failure_stops_without_exposing_key(self):
        p = self.provider()
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError("https://api.supadata.ai", 402, "sensitive response", {}, None)
        p.open = fail
        r = p.check(VIDEO)
        self.assertEqual(p.stopped, "provider_quota")
        self.assertNotIn("sensitive", json.dumps(r))
        self.assertEqual(p.report()["reserved_requests"], 1)

    def test_public_reader_block_does_not_stop_configured_fallback(self):
        s = MemoryStore()
        for vid in ("abcDEFG1234", "abcDEFG5678"):
            s.write("b", [record("sampled_videos", "b", "sample:"+vid, {"selected_for_sample": True}, vid),
                          record("candidate_videos", "b", "source:"+vid, dict(VIDEO, video_id=vid), vid)])
        class Blocked:
            blocked = "IpBlocked"
            def check(self, source, **kw):
                return {"eligible": False, "status": "english_access_unverified", "failure_reason": "IpBlocked"}
        p = self.provider(s)
        p.batch = "b"
        with patch("eiim.language_access.EnglishCaptionAccess", Blocked), patch.object(SupadataCaptions, "from_environment", return_value=p):
            report = retrieve_retained_captions(s, "b")
        self.assertEqual(report["new_saved_transcripts"], 2)
        self.assertEqual(report["coverage"]["saved_transcripts"], 2)

    def test_full_sample_is_not_complete_when_only_eligible_subset_is_done(self):
        s = fixtures.HybridTests().make_transcript_store()
        s.batch({"id": "2026-W40"}, "test")
        s.write("2026-W40", [record("sampled_videos", "2026-W40", "pending", {"selected_for_sample": True}, "pending")])
        class Fake:
            cfg = {"model": "test"}
            def request(self, *args):
                x = fixtures.label(); x["comments"] = []
                return {"parsed": x, "model_name": "test", "model_version": "test", "classification_timestamp": "2026-10-05T00:00:00Z"}
        report = reclassify(s, "2026-W40", Fake())
        self.assertEqual(report["status"], "awaiting_transcripts")
        self.assertEqual(report["classification_status"], "complete")
        self.assertEqual(report["coverage"]["sampled_videos"], 2)
        self.assertEqual(report["classified_videos"], 1)
        self.assertFalse(report["human_review_required_for_classification"])
