"""Versioned English review eligibility; source language is never overwritten."""

from .core import now

POLICY_VERSION = "english-access-1.0"


def primary_language(code):
    return (code or "und").lower().replace("_", "-").split("-")[0]


def audio_language(video):
    return (
        video.get("original_audio_language")
        or video.get("raw_api_response", {})
        .get("snippet", {})
        .get("defaultAudioLanguage")
        or "und"
    )


def declared_access(video):
    language = audio_language(video)
    return {
        "english_access_video_id": video["video_id"],
        "policy_version": POLICY_VERSION,
        "original_language": language,
        "language_basis": (
            "publisher_audio_metadata" if language != "und" else "unknown"
        ),
        "eligible": primary_language(language) == "en",
        "status": (
            "english_audio"
            if primary_language(language) == "en"
            else "english_access_unverified"
        ),
        "checked_at": now(),
        "transcript_english": [],
    }


def access_records(rows):
    records = {}
    for r in sorted(rows, key=lambda r: r["payload"].get("checked_at", "")):
        p = r["payload"]
        if (
            not r.get("purged_at")
            and p.get("policy_version") == POLICY_VERSION
            and p.get("english_access_video_id")
        ):
            key = (r["batch_id"], p["english_access_video_id"])
            previous = records.get(key, {})
            # A later failed lookup must not erase already saved source evidence.
            if (previous.get("eligible") and previous.get("transcript_english")
                    and not (p.get("eligible") and p.get("transcript_english"))):
                continue
            records[key] = p
    return records


def video_access(video, batch, records):
    return records.get((batch, video.get("video_id")), declared_access(video))


def caption_state(access):
    if access.get("eligible") and any(s.get("text", "").strip() for s in access.get("transcript_english", [])):
        return "saved"
    if access.get("failure_reason") in {"IpBlocked", "RequestBlocked", "AudioAccessBlocked"} or access.get("direct_failure_reason") in {"IpBlocked", "RequestBlocked"}:
        return "blocked"
    if access.get("status") == "no_english_captions" or access.get("failure_reason") == "TranscriptsDisabled":
        return "unavailable"
    return "unverified"


class EnglishCaptionAccess:
    """Public tracks only. No cookies, proxy bypass, or invented availability."""

    def __init__(self, api=None):
        self.api = api
        self.blocked = None

    def check(self, video, retrieve_english_audio=False):
        result = declared_access(video)
        if result["eligible"] and not retrieve_english_audio:
            return result
        result["transcript_checked"] = True
        if self.blocked:
            return dict(result, failure_reason=self.blocked)
        if self.api is None:
            from requests import Session
            from youtube_transcript_api import YouTubeTranscriptApi

            class BoundedSession(Session):
                def request(self, *args, **kwargs):
                    kwargs.setdefault("timeout", 15)
                    return super().request(*args, **kwargs)

            self.api = YouTubeTranscriptApi(http_client=BoundedSession())
        try:
            tracks = list(self.api.list(video["video_id"]))
            generated = [t for t in tracks if t.is_generated]
            if result["original_language"] == "und" and len(generated) == 1:
                result.update(
                    original_language=generated[0].language_code,
                    language_basis="automatic_caption_source_language",
                )
            english = sorted(
                [t for t in tracks if primary_language(t.language_code) == "en"],
                key=lambda t: t.is_generated,
            )
            choices = [(t, False) for t in english]
            # User explicitly accepts successful YouTube English auto-translation.
            for t in tracks:
                if (
                    primary_language(t.language_code) != "en"
                    and t.is_translatable
                    and any(
                        (
                            x.get("language_code")
                            if isinstance(x, dict)
                            else x.language_code
                        )
                        == "en"
                        for x in t.translation_languages
                    )
                ):
                    choices.append((t, True))
            failures = []
            for original, auto_translated in choices:
                try:
                    translated = original.translate("en") if auto_translated else original
                    fetched = translated.fetch()
                except Exception as error:
                    reason = type(error).__name__
                    if reason in {"RequestBlocked", "IpBlocked"}:
                        self.blocked = reason
                        return dict(result, failure_reason=reason)
                    failures.append(reason)
                    continue
                segments = fetched.to_raw_data()
                if not segments or not any(s.get("text", "").strip() for s in segments):
                    continue
                return dict(
                    result,
                    eligible=True,
                    status=(
                        "english_auto_translated_captions"
                        if auto_translated
                        else "english_caption_track"
                    ),
                    caption_source_language=original.language_code,
                    caption_is_generated=original.is_generated,
                    caption_translation=(
                        "youtube_auto_translation" if auto_translated else "none"
                    ),
                    transcript_language="en",
                    transcript_english=segments,
                )
            if failures:
                return dict(result, failure_reason=failures[-1])
            return dict(
                result,
                status="english_audio" if result["eligible"] else "no_english_captions",
            )
        except Exception as error:
            reason = type(error).__name__
            if reason in {
                "RequestBlocked",
                "IpBlocked",
            }:
                self.blocked = reason
            return dict(result, failure_reason=reason)


TRANSLATION_VERSION = "english-comment-1.1"


def translated_comment(comment, classifier):
    """Keep the original text/language and provide separate English labeling text."""
    original = comment["text_original"]
    language = comment.get("original_language", comment.get("language", "und"))
    result = classifier.translate(original)
    return {
        "comment_translation_id": comment["comment_id"],
        "original_language": language,
        "translation_detected_language": result["parsed"]["source_language"],
        "text_english": result["parsed"]["text_english"],
        "translation_version": TRANSLATION_VERSION,
        "translation_status": (
            "original_english_verified"
            if primary_language(result["parsed"]["source_language"]) == "en"
            else "machine_translated"
        ),
        "translation_model": result["model_version"],
        "translated_at": result["classification_timestamp"],
        "label_language": "en",
    }
