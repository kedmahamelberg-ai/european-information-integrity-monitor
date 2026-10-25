"""Bounded audio recovery, with an optional private YouTube cookie file."""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .core import now
from .language_access import declared_access, primary_language
from .youtube_session import cookie_file

VERSION = "whisper-audio-1.1"
MODEL = "medium"
MAX_DURATION = 7200
MAX_BYTES = 256 * 1024 * 1024
TIMESTAMP_TOLERANCE = 0.25


def speech_coverage(regions, segments):
    """Account for every VAD speech interval, allowing timestamp precision only."""
    intervals = sorted((max(0, s["start"] - TIMESTAMP_TOLERANCE),
                        s["end"] + TIMESTAMP_TOLERANCE) for s in segments)
    gaps = []
    total = sum(r["end"] - r["start"] for r in regions)
    for region in regions:
        cursor = region["start"]
        for start, end in intervals:
            if end <= cursor:
                continue
            if start >= region["end"]:
                break
            if start > cursor:
                gaps.append({"start": cursor, "end": min(start, region["end"])})
            cursor = max(cursor, end)
            if cursor >= region["end"]:
                break
        if cursor < region["end"]:
            gaps.append({"start": cursor, "end": region["end"]})
    gaps = [g for g in gaps if g["end"] - g["start"] > 0.02]
    missing = sum(g["end"] - g["start"] for g in gaps)
    return {"complete": total > 0 and not gaps, "speech_seconds": total,
            "uncovered_seconds": missing, "uncovered_spans": gaps,
            "timestamp_tolerance_seconds": TIMESTAMP_TOLERANCE}


def assess_segments(segments, regions):
    """Silence is not missing speech; uncertain speech is never silently removed."""
    kept, rejected, silence = [], [], 0
    for segment in segments:
        s = vars(segment) if hasattr(segment, "__dict__") else segment
        start, end = s["start"], s["end"]
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or not 0 <= start < end):
            raise ValueError("Invalid transcription interval")
        overlaps_speech = any(min(end, r["end"]) > max(start, r["start"]) for r in regions)
        scores = [s["avg_logprob"], s["no_speech_prob"], s["compression_ratio"]]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in scores):
            raise ValueError("Invalid transcription confidence")
        # Require agreement between independent VAD and Whisper before calling
        # a discarded segment silence. Keep confident words at quiet boundaries.
        if not overlaps_speech and s["no_speech_prob"] > .6 and s["avg_logprob"] < -1:
            silence += 1
            continue
        # A high no-speech probability alone does not veto confident speech.
        # Match Whisper's joint silence/confidence test, while still rejecting
        # unresolved low-confidence or repetitive speech after decoding fallback.
        reason = None
        if s["avg_logprob"] < -1:
            reason = "uncertain_speech"
        elif s["compression_ratio"] > 2.4:
            reason = "repetitive_speech"
        elif not s["text"].strip():
            reason = "empty_speech"
        if reason:
            rejected.append({"start": start, "end": end, "reason": reason})
        else:
            kept.append({"text": s["text"].strip(), "start": start, "end": end})
    return {"segments": kept, "discarded_segments": len(rejected),
            "rejected_speech_spans": rejected, "ignored_non_speech_segments": silence,
            "speech_coverage": speech_coverage(regions, kept)}


def english_result(video, speech):
    """Only nonempty, timestamped model output becomes classification evidence."""
    result = declared_access(video)
    result.update(eligible=False, transcript_checked=True,
                  audio_recovery_version=VERSION, caption_provider="faster-whisper",
                  caption_retrieval_mode="public_audio", transcription_model=speech.get("model", MODEL),
                  caption_is_generated=True, transcript_complete=False)
    language = speech.get("language", "und")
    confidence = speech.get("language_probability", 0)
    if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}", language) or language == "und" or type(confidence) not in (int, float) or not 0.6 <= confidence <= 1:
        return dict(result, failure_reason="AudioLanguageUncertain")
    if speech.get("task") != "translate" or speech.get("output_language") != "en":
        return dict(result, failure_reason="AudioEnglishTranslationRequired")
    duration = speech.get("duration")
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= MAX_DURATION + 1:
        return dict(result, failure_reason="AudioInvalidSegments")
    segments = speech.get("segments", [])
    if not segments:
        return dict(result, failure_reason="AudioNoUsableSpeech")
    clean = []
    for s in segments:
        text = s.get("text", "").strip()
        start, end = s.get("start"), s.get("end")
        if (not text or type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or not 0 <= start < end <= duration + TIMESTAMP_TOLERANCE
                or (clean and start < clean[-1]["start"])):
            return dict(result, failure_reason="AudioInvalidSegments")
        clean.append({"text": text, "start": start, "duration": end - start})
    words = re.findall(r"\w+", " ".join(s["text"] for s in clean).casefold())
    if not words or (len(words) >= 20 and len(set(words)) < 10):
        return dict(result, failure_reason="AudioNoUsableSpeech")
    if result["original_language"] == "und":
        result.update(original_language=language, language_basis="whisper_language_detection")
    coverage = speech.get("speech_coverage", {})
    # Removing the fixed word minimum must not admit a few words standing in
    # for a long speech interval. This is a low-density safety gate, not a
    # requirement that short clips contain twenty words.
    speech_seconds = coverage.get("speech_seconds", 0)
    plausible_density = (type(speech_seconds) in (int, float)
                         and math.isfinite(speech_seconds)
                         and 0 < speech_seconds <= duration
                         and len(words) >= speech_seconds / 3)
    complete = (speech.get("audio_complete") is True
                and speech.get("speech_coverage", {}).get("complete") is True
                and speech.get("discarded_segments") == 0 and plausible_density)
    return dict(result, eligible=complete,
                status="english_audio_transcription" if complete else "english_audio_incomplete",
                failure_reason="AudioIncompleteTranscript" if not complete else None,
                caption_source_language=language,
                caption_translation="none" if primary_language(language) == "en" else "whisper_translation",
                transcript_language="en", transcript_english=clean,
                transcript_complete=complete,
                transcription_language_probability=confidence,
                transcription_quality="automatic_unreviewed",
                audio_duration_seconds=duration,
                transcript_validation=dict({k: speech.get(k) for k in (
                    "audio_complete", "expected_duration", "speech_coverage",
                    "rejected_speech_spans", "ignored_non_speech_segments")},
                    plausible_speech_density=plausible_density))


class AudioTranscripts:
    def __init__(self, max_videos=80, max_seconds=2700, runner=subprocess.run, clock=time.monotonic):
        self.max_videos, self.max_seconds = max_videos, max_seconds
        self.runner, self.clock = runner, clock
        self.started = clock()
        self.attempted = self.saved = self.blocked_attempts = 0
        self.stopped = None
        self.download_errors = {}

    @classmethod
    def from_environment(cls):
        if os.environ.get("EIIM_ENABLE_AUDIO_TRANSCRIPTION") != "true":
            return None
        return cls()

    def report(self):
        return {"configured": True, "provider": "faster-whisper", "model": MODEL,
                "attempted_videos": self.attempted, "saved_transcripts": self.saved,
                "max_videos": self.max_videos, "max_seconds": self.max_seconds,
                "stopped": self.stopped, "paid_api": False,
                "authenticated_download": bool(cookie_file()),
                "download_errors": self.download_errors}

    def check(self, video):
        if self.stopped:
            return None
        if self.attempted >= self.max_videos or self.clock() - self.started >= self.max_seconds:
            self.stopped = "audio_run_limit"
            return None
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video.get("video_id", "")):
            return None
        self.attempted += 1
        result = dict(declared_access(video), eligible=False, transcript_checked=True,
                      audio_recovery_version=VERSION, audio_attempted_at=now(),
                      audio_authenticated=bool(cookie_file()))
        # A process timeout bounds downloads, model loading and CPU transcription.
        # The parent owns this directory so a killed worker cannot leave raw audio.
        with tempfile.TemporaryDirectory(prefix="eiim-audio-") as folder:
            target = str(Path(folder) / "result.json")
            try:
                completed = self.runner(
                    [sys.executable, "-m", "eiim.audio_transcripts", video["video_id"], folder],
                    capture_output=True, text=True, timeout=900, check=False,
                )
                if completed.returncode or not Path(target).exists():
                    result["failure_reason"] = "AudioWorkerFailed"
                else:
                    speech = json.loads(Path(target).read_text())
                    if speech.get("failure_reason"):
                        result["failure_reason"] = speech["failure_reason"]
                        category = speech.get("audio_download_error")
                        if category in {"youtube_bot_check", "youtube_sign_in", "http_403", "http_429", "format_unavailable", "javascript_runtime", "private_video", "video_unavailable", "other_download_error"}:
                            result["audio_download_error"] = category
                    else:
                        result.update(english_result(video, speech))
            except subprocess.TimeoutExpired:
                result["failure_reason"] = "AudioTimedOut"
            except (OSError, ValueError, TypeError):
                result["failure_reason"] = "AudioWorkerFailed"
        category = result.get("audio_download_error")
        if category:
            self.download_errors[category] = self.download_errors.get(category, 0) + 1
        reason = result.get("failure_reason")
        # Video-specific download failures must not halt other sources.
        # Only repeated authentication or rate-limit failures stop the session.
        if reason == "AudioAccessBlocked":
            self.blocked_attempts += 1
            if self.blocked_attempts >= 3:
                self.stopped = "audio_access_unavailable"
        else:
            self.blocked_attempts = 0
        if reason in {"AudioDependenciesUnavailable", "AudioModelUnavailable"}:
            self.stopped = reason
        self.saved += bool(result.get("eligible") and result.get("transcript_english"))
        return result


def download_public_audio(video_id, folder):
    try:
        import yt_dlp
    except ImportError:
        return {"failure_reason": "AudioDependenciesUnavailable"}

    class Quiet:
        def debug(self, *args): pass
        def warning(self, *args): pass
        def error(self, *args): pass

    def bound(progress):
        if progress.get("downloaded_bytes", 0) > MAX_BYTES:
            raise ValueError("Audio size limit")

    options = {"format": "bestaudio/best", "noplaylist": True,
               "outtmpl": str(Path(folder) / "audio.%(ext)s"),
               "socket_timeout": 15, "retries": 0, "fragment_retries": 0,
               "max_filesize": MAX_BYTES, "quiet": True, "no_warnings": True,
               "logger": Quiet(), "progress_hooks": [bound],
               "js_runtimes": {"node": {}}}
    try:
        cookies = cookie_file()
        if cookies:
            # yt-dlp may update its jar. Keep that private copy inside the
            # parent's temporary directory, removed even if the worker times out.
            private_cookie = Path(folder) / 'cookies.txt'
            shutil.copyfile(cookies, private_cookie)
            private_cookie.chmod(0o600)
            options['cookiefile'] = str(private_cookie)
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info("https://www.youtube.com/watch?v=" + video_id, download=False)
            if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
                return {"failure_reason": "AudioLiveOrUpcoming"}
            duration = info.get("duration")
            if not isinstance(duration, (int, float)) or not 0 < duration <= MAX_DURATION:
                return {"failure_reason": "AudioDurationLimit"}
            downloader.process_info(info)
        media = [p for p in Path(folder).glob("audio.*") if p.suffix not in {".part", ".ytdl"}]
        if len(media) != 1 or not 0 < media[0].stat().st_size <= MAX_BYTES:
            return {"failure_reason": "AudioDownloadUnavailable"}
    except Exception as error:
        message = str(error).lower()
        blocked = any(s in message for s in ["sign in", "not a bot", "429", "403", "blocked", "private video", "age-restricted"])
        category = "other_download_error"
        for token, name in [("not a bot", "youtube_bot_check"), ("sign in", "youtube_sign_in"),
                            ("403", "http_403"), ("429", "http_429"),
                            ("requested format", "format_unavailable"), ("javascript", "javascript_runtime"),
                            ("private video", "private_video"), ("unavailable", "video_unavailable")]:
            if token in message:
                category = name
                break
        return {"failure_reason": "AudioAccessBlocked" if blocked else "AudioDownloadUnavailable",
                "audio_download_error": category}
    return {"path": str(media[0]), "duration": duration}


def transcribe_audio_file(path, expected_duration, *, model_name=MODEL):
    """One translation pass over the full audio; no paid API or retry model."""
    try:
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)
    except Exception:
        return {"failure_reason": "AudioModelUnavailable"}
    try:
        waveform = decode_audio(path, sampling_rate=16000)
        duration = len(waveform) / 16000
        # Unpadded speech intervals provide a separate coverage check. Model VAD
        # keeps its normal context padding, so words at boundaries are retained.
        spans = get_speech_timestamps(waveform, VadOptions(min_silence_duration_ms=500, speech_pad_ms=0))
        regions = [{"start": s["start"] / 16000, "end": s["end"] / 16000} for s in spans]
        if not regions:
            return {"failure_reason": "AudioNoUsableSpeech"}
        segments, info = model.transcribe(waveform, task="translate", beam_size=5,
                                         vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
                                         condition_on_previous_text=False)
        # Language detection is available before decoding the generator. Do not
        # spend the whole worker budget on speech that cannot pass this gate.
        if not math.isfinite(info.language_probability) or info.language_probability < 0.6:
            return {"failure_reason": "AudioLanguageUncertain", "model": model_name,
                    "language": info.language, "language_probability": info.language_probability,
                    "duration": duration}
        assessed = assess_segments(list(segments), regions)
        return dict(assessed, language=info.language,
                model=model_name, task="translate", output_language="en",
                expected_duration=expected_duration,
                audio_complete=abs(duration - expected_duration) <= max(.75, min(2, expected_duration * .002)),
                language_probability=info.language_probability,
                duration=duration)
    except Exception:
        return {"failure_reason": "AudioTranscriptionFailed"}


def transcribe_public_audio(video_id, folder):
    audio = download_public_audio(video_id, folder)
    if audio.get("failure_reason"):
        return audio
    return transcribe_audio_file(audio["path"], audio["duration"])


if __name__ == "__main__":
    video_id, folder = sys.argv[1:]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise SystemExit(2)
    Path(folder, "result.json").write_text(json.dumps(transcribe_public_audio(video_id, folder)))
