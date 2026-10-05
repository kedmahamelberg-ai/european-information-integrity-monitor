"""Optional native-caption API. Public video URLs only; never audio generation.

A durable reservation before each request bounds usage across daily restarts and
batches. The existing shared workflow concurrency serializes these reservations.
"""
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .core import now, digest
from .language_access import declared_access, primary_language
from .storage import record


class SupadataCaptions:
    endpoint = "https://api.supadata.ai/v1/transcript"

    @classmethod
    def from_environment(cls, store, batch):
        key = os.environ.get("SUPADATA_API_KEY")
        if not key:
            return None
        return cls(store, batch, key, int(os.environ.get("EIIM_CAPTION_MONTHLY_REQUEST_LIMIT", "100")))

    def __init__(self, store, batch, key, limit=100, opener=None, sleeper=None):
        if not 0 <= limit <= 100000:
            raise ValueError("Caption monthly request limit must be 0–100000")
        self.store, self.batch, self.key, self.limit = store, batch, key, limit
        self.open = opener or urllib.request.urlopen
        self.sleep = sleeper or time.sleep
        self.month = now()[:7]
        self.attempted = {
            r["payload"]["caption_provider_video_key"]
            for r in store.read("cost_events")
            if r["payload"].get("caption_provider_reservation") == "supadata-native-v1"
            and r["payload"].get("month") == self.month
        }
        self.stopped = None
        self.new_requests = 0

    def report(self):
        return {"configured": True, "provider": "supadata", "mode": "native",
                "monthly_request_limit": self.limit, "month": self.month,
                "reserved_requests": len(self.attempted), "new_requests": self.new_requests,
                "stopped": self.stopped}

    def fetch(self, url):
        request = urllib.request.Request(url, headers={"x-api-key": self.key})
        with self.open(request, timeout=45) as response:
            return response.status, json.load(response)

    def check(self, video):
        vid = video["video_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            raise ValueError("Invalid public YouTube video ID")
        video_key = digest(vid)
        if self.stopped or video_key in self.attempted:
            return None
        if len(self.attempted) >= self.limit:
            self.stopped = "monthly_request_limit"
            return None
        # Reserve even if a timeout/crash occurs: never assume the provider did
        # not bill a request. Failed IDs can be retried in a later calendar month.
        self.store.write(self.batch, [record("cost_events", self.batch,
            f"{self.batch}:caption-provider:supadata:{self.month}:{video_key}",
            {"caption_provider_reservation": "supadata-native-v1", "month": self.month,
             "caption_provider_video_key": video_key, "reserved_at": now(),
             "kind": "caption_native_requests", "amount": 1})])
        self.attempted.add(video_key)
        self.new_requests += 1
        self.sleep(1.1)  # Free-plan rate limit is one request per second.
        result = dict(declared_access(video), eligible=False, transcript_checked=True,
                      status="english_access_unverified", caption_provider="supadata",
                      caption_retrieval_mode="native", transcript_english=[])
        query = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}",
                                        "lang": "en", "text": "false", "mode": "native"})
        try:
            status, data = self.fetch(self.endpoint + "?" + query)
            if not isinstance(data, dict):
                raise ValueError("Invalid caption response")
            if status == 202:
                job = data.get("jobId", "")
                if not isinstance(job, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", job):
                    raise ValueError("Invalid job ID")
                for _ in range(20):
                    self.sleep(2)
                    _, data = self.fetch(self.endpoint + "/" + job)
                    if not isinstance(data, dict):
                        raise ValueError("Invalid job response")
                    if data.get("status") in {"completed", "failed"}:
                        break
                if data.get("status") != "completed":
                    return dict(result, failure_reason="CaptionProviderJobIncomplete")
                data = data.get("result", data)
            elif status == 206:
                return dict(result, status="no_english_captions")
            if not isinstance(data, dict):
                raise ValueError("Invalid caption result")
            language = data.get("lang", "und")
            result["caption_returned_language"] = language
            result["caption_available_languages"] = data.get("availableLangs", [])
            # A preferred lang=en is not a guarantee: the API may return its
            # default language. Never label foreign text as English.
            if primary_language(language) != "en":
                return dict(result, failure_reason="EnglishTrackNotReturned")
            content = data.get("content")
            if not isinstance(content, list):
                raise ValueError("Timestamped caption segments required")
            segments = []
            for item in content:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    raise ValueError("Invalid caption segment")
                if primary_language(item.get("lang", language)) != "en":
                    return dict(result, failure_reason="EnglishTrackNotReturned")
                start, duration = float(item["offset"]) / 1000, float(item["duration"]) / 1000
                if not all(math.isfinite(x) and x >= 0 for x in (start, duration)):
                    raise ValueError("Invalid caption timing")
                if item["text"].strip():
                    segments.append({"text": item["text"], "start": start, "duration": duration})
            if not segments:
                return dict(result, failure_reason="EmptyCaptionResponse")
            return dict(result, eligible=True, status="english_caption_track",
                        caption_source_language="en", caption_translation="provider_unspecified",
                        transcript_language="en", transcript_english=segments)
        except urllib.error.HTTPError as error:
            if error.code in {401, 402, 429}:
                self.stopped = {401: "provider_authentication", 402: "provider_quota", 429: "provider_rate_limit"}[error.code]
            return dict(result, failure_reason=f"CaptionProviderHTTP{error.code}")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # No response bodies, URLs with tokens, or credential values in logs.
            return dict(result, failure_reason="CaptionProviderInvalidOrUnavailable")
