"""Timestamped public counters, kept separate from sampled comment records."""

from datetime import datetime


def engagement(source):
    raw = source.get("raw_api_response", {})
    stats = raw.get("statistics", {})

    def count(key):
        value = stats.get(key)
        if isinstance(value, bool):
            return None
        try:
            result = int(value)
            return result if result >= 0 else None
        except (ValueError, TypeError):
            return None

    views, likes, comments = (
        count(k) for k in ["viewCount", "likeCount", "commentCount"]
    )
    captured = source.get("retrieved_at")
    published = source.get("published_at")
    age = None
    if captured and published:
        try:
            age = max(
                0,
                (
                    datetime.fromisoformat(captured.replace("Z", "+00:00"))
                    - datetime.fromisoformat(published.replace("Z", "+00:00"))
                ).total_seconds()
                / 3600,
            )
        except ValueError:
            pass
    return {
        "views": views,
        "likes": likes,
        "total_comments": comments,
        "shares": None,
        "shares_status": "not_publicly_available",
        "captured_at": captured,
        "published_at": published,
        "age_hours_at_capture": age,
        "likes_per_1000_views": (
            likes / views * 1000 if views and likes is not None else None
        ),
        "comments_per_1000_views": (
            comments / views * 1000 if views and comments is not None else None
        ),
        "duration": raw.get("contentDetails", {}).get("duration"),
        "provenance": "original_youtube_videos_statistics_snapshot",
    }
