"""Bounded public-audio recovery. No credentials, proxies or paid speech API."""

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .core import now
from .language_access import declared_access, primary_language

VERSION = "whisper-audio-1.0"
MODEL = "small"
MAX_DURATION = 7200
MAX_BYTES = 256 * 1024 * 1024


def english_result(video, speech):
    """Only nonempty, timestamped model output becomes classification evidence."""
    result = declared_access(video)
    result.update(eligible=False, transcript_checked=True,
                  audio_recovery_version=VERSION, caption_provider="faster-whisper",
                  caption_retrieval_mode="public_audio", transcription_model=MODEL,
                  caption_is_generated=True)
    language = speech.get("language", "und")
    confidence = speech.get("language_probability", 0)
    if not re.fullmatch(r"[a-z]{2,3}", language) or language == "und" or not isinstance(confidence, (int, float)) or not 0.6 <= confidence <= 1:
        return dict(result, failure_reason="AudioLanguageUncertain")
    segments = speech.get("segments", [])
    if not segments:
        return dict(result, failure_reason="AudioNoUsableSpeech")
    clean = []
    for s in segments:
        text = s.get("text", "").strip()
        start, end = s.get("start"), s.get("end")
        if (not text or type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or not 0 <= start < end <= MAX_DURATION + 1
                or (clean and start < clean[-1]["start"])):
            return dict(result, failure_reason="AudioInvalidSegments")
        clean.append({"text": text, "start": start, "duration": end - start})
    words = re.findall(r"\w+", " ".join(s["text"] for s in clean).casefold())
    if len(words) < 20 or len(set(words)) < 10:
        return dict(result, failure_reason="AudioNoUsableSpeech")
    if result["original_language"] == "und":
        result.update(original_language=language, language_basis="whisper_language_detection")
    return dict(result, eligible=True, status="english_audio_transcription",
                caption_source_language=language,
                caption_translation="none" if primary_language(language) == "en" else "whisper_translation",
                transcript_language="en", transcript_english=clean,
                transcript_complete=not speech.get("discarded_segments", 0),
                transcription_language_probability=confidence,
                transcription_quality="automatic_unreviewed",
                audio_duration_seconds=speech.get("duration"))


class AudioTranscripts:
    def __init__(self, max_videos=80, max_seconds=2700, runner=subprocess.run, clock=time.monotonic):
        self.max_videos, self.max_seconds = max_videos, max_seconds
        self.runner, self.clock = runner, clock
        self.started = clock()
        self.attempted = self.saved = self.blocked_attempts = 0
        self.stopped = None

    @classmethod
    def from_environment(cls):
        if os.environ.get("EIIM_ENABLE_AUDIO_TRANSCRIPTION") != "true":
            return None
        return cls()

    def report(self):
        return {"configured": True, "provider": "faster-whisper", "model": MODEL,
                "attempted_videos": self.attempted, "saved_transcripts": self.saved,
                "max_videos": self.max_videos, "max_seconds": self.max_seconds,
                "stopped": self.stopped, "paid_api": False}

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
                      audio_recovery_version=VERSION, audio_attempted_at=now())
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
                    else:
                        result.update(english_result(video, speech))
            except subprocess.TimeoutExpired:
                result["failure_reason"] = "AudioTimedOut"
            except (OSError, ValueError, TypeError):
                result["failure_reason"] = "AudioWorkerFailed"
        reason = result.get("failure_reason")
        if reason in {"AudioAccessBlocked", "AudioDownloadUnavailable"}:
            self.blocked_attempts += 1
            if self.blocked_attempts >= 3:
                self.stopped = "audio_access_unavailable"
        else:
            self.blocked_attempts = 0
        if reason in {"AudioDependenciesUnavailable", "AudioModelUnavailable"}:
            self.stopped = reason
        self.saved += bool(result.get("transcript_english"))
        return result


def transcribe_public_audio(video_id, folder):
    try:
        import yt_dlp
        from faster_whisper import WhisperModel
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
               "logger": Quiet(), "progress_hooks": [bound]}
    try:
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
        return {"failure_reason": "AudioAccessBlocked" if blocked else "AudioDownloadUnavailable"}
    try:
        model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)
    except Exception:
        return {"failure_reason": "AudioModelUnavailable"}
    try:
        segments, info = model.transcribe(str(media[0]), task="translate", beam_size=5,
                                         vad_filter=True, condition_on_previous_text=False)
        kept, discarded = [], 0
        for s in segments:
            if s.no_speech_prob > 0.6 or s.avg_logprob < -1 or s.compression_ratio > 2.4:
                discarded += 1
                continue
            kept.append({"text": s.text.strip(), "start": s.start, "end": s.end})
        return {"segments": kept, "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration, "discarded_segments": discarded}
    except Exception:
        return {"failure_reason": "AudioTranscriptionFailed"}


if __name__ == "__main__":
    video_id, folder = sys.argv[1:]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise SystemExit(2)
    Path(folder, "result.json").write_text(json.dumps(transcribe_public_audio(video_id, folder)))
