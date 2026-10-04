import unittest
from types import SimpleNamespace
from eiim.language_access import EnglishCaptionAccess, translated_comment


class Track:
    def __init__(
        self, language, generated=False, translatable=False, text="English evidence"
    ):
        self.language_code = language
        self.is_generated = generated
        self.is_translatable = translatable
        self.translation_languages = (
            [SimpleNamespace(language_code="en")] if translatable else []
        )
        self.text = text

    def translate(self, language):
        return Track(language, True, text=self.text)

    def fetch(self):
        return SimpleNamespace(
            to_raw_data=lambda: [{"text": self.text, "start": 0, "duration": 2}]
        )


class LanguageAccessTests(unittest.TestCase):
    def check(self, language, tracks):
        return EnglishCaptionAccess(SimpleNamespace(list=lambda _: tracks)).check(
            {"video_id": "fixture", "original_audio_language": language}
        )

    def test_audio_language_not_english_title_controls_access(self):
        self.assertTrue(self.check("en-GB", [])["eligible"])
        self.assertFalse(self.check("de", [])["eligible"])
        self.assertFalse(self.check("und", [])["eligible"])

    def test_retrieved_auto_translation_preserves_source_language(self):
        result = self.check("de-AT", [Track("de", True, True)])
        self.assertTrue(result["eligible"])
        self.assertEqual(result["original_language"], "de-AT")
        self.assertEqual(result["status"], "english_auto_translated_captions")
        self.assertEqual(result["caption_source_language"], "de")
        self.assertTrue(result["transcript_english"])

    def test_empty_or_failed_caption_fetch_is_not_eligible(self):
        self.assertFalse(self.check("fr", [Track("en", text="")])["eligible"])

        class IpBlocked(Exception):
            pass

        def fail(_):
            raise IpBlocked()

        provider = EnglishCaptionAccess(SimpleNamespace(list=fail))
        result = provider.check(
            {"video_id": "fixture", "original_audio_language": "de"}
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], "english_access_unverified")
        self.assertEqual(result["failure_reason"], "IpBlocked")

    def test_comment_translation_does_not_overwrite_original(self):
        source = {
            "comment_id": "one",
            "text_original": "Não concordo",
            "language": "pt",
            "confidence": 0.99,
        }
        model = SimpleNamespace(
            translate=lambda text: {
                "parsed": {"text_english": "I disagree", "source_language": "pt"},
                "model_version": "fixture",
                "classification_timestamp": "2026-10-04T00:00:00Z",
            }
        )
        translated = translated_comment(source, model)
        self.assertEqual(source["text_original"], "Não concordo")
        self.assertEqual(source["language"], "pt")
        self.assertEqual(translated["text_english"], "I disagree")
        self.assertEqual(translated["label_language"], "en")
        self.assertEqual(translated["original_language"], "pt")
        english = translated_comment(
            dict(source, language="en", text_original="Original English"), None
        )
        self.assertEqual(english["translation_status"], "original_english")
