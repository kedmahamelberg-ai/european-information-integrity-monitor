"""Private review packets and strict imports for the transcript-based taxonomy."""

import json
from pathlib import Path
from .core import ROOT, config, digest, now
from .hybrid import VERSION, retained_inputs, labels, latest_labels
from .review_sampling import sample_plan, assignment
from .storage import record
from .engagement import engagement

VIDEO_FIELDS = ["relevance", "topics", "roles"]
EXECUTION = config("hybrid")["execution"]
REFERENCE_FIELDS = ["speaker", "summary", "target", "speaker_sentiment"]
COMMENT_FIELDS = [
    "response_focus",
    "alignment",
    "stance_target",
    "sentiment",
    "sentiment_target",
]


def video_values(label):
    return {
        **{k: label[k] for k in VIDEO_FIELDS},
        **{"reference:" + k: label["content_reference"][k] for k in REFERENCE_FIELDS},
        **{"execution:" + e["category"]: e["status"] for e in label["execution"]},
    }


def media_evidence(source, access):
    """Observed metadata/caption cues only; no inferred audio or thumbnail labels."""
    import re

    thumbnails = (
        source.get("raw_api_response", {}).get("snippet", {}).get("thumbnails", {})
    )
    thumbnail = next(
        (
            thumbnails[k].get("url")
            for k in ["maxres", "standard", "high", "medium", "default"]
            if thumbnails.get(k, {}).get("url")
        ),
        None,
    )
    cues = [
        s
        for s in access.get("transcript_english", [])
        if re.search(
            r"\[(?:music|instrumental|singing)[^]]*\]|[♪♫]", s.get("text", ""), re.I
        )
    ]
    return {
        "thumbnail_url": thumbnail,
        "music_caption_cues": cues,
        "audio_analysis": "not_performed",
    }


def packet(store, batch):
    videos, comments, translations, _ = retained_inputs(store, batch)
    plan = sample_plan(batch, videos)
    items = []
    for row in latest_labels(labels(store, batch)):
        vid, p = row["video_id"], row["payload"]
        if vid not in videos:
            continue
        source, access = videos[vid]
        items.append(
            {
                "id": row["id"],
                "hash": row.get("payload_hash", digest(p)),
                "batch": batch,
                "video_id": vid,
                "title": source["title"],
                "channel": source.get("channel", ""),
                "countries": [
                    {
                        "code": code,
                        "name": next(
                            (
                                c["country_name"]
                                for c in config("countries")["countries"]
                                if c["iso2"] == code
                            ),
                            code,
                        ),
                    }
                    for code in source.get("countries", [])
                ],
                "country_basis": "title_and_description",
                "description": source.get("description", ""),
                "source_language": access["original_language"],
                "caption_status": access.get("status"),
                "media_evidence": media_evidence(source, access),
                "transcript": access["transcript_english"],
                "transcript_truncated": p["transcript_truncated"],
                "label": p["label"],
                "model_values": video_values(p["label"]),
                "model": p["model_version"],
                "prior_reviews": [
                    r["payload"]
                    for r in store.read("human_validation", batch)
                    if not r.get("purged_at")
                    and r.get("video_id") == vid
                    and r["payload"].get("item_type") == "hybrid_video"
                    and r["payload"].get("version") != VERSION
                ],
                "review_assignment": assignment(plan, vid),
                "engagement": engagement(source),
                "comments": [
                    {
                        **c,
                        "translation": translations.get(c["comment_id"], {}),
                        "prior_reviews": [
                            r["payload"]
                            for r in store.read("human_validation", batch)
                            if not r.get("purged_at")
                            and r["payload"].get("comment_id") == c["comment_id"]
                            and r["payload"].get("version") != VERSION
                        ],
                        "ai": next(
                            (
                                x
                                for x in p["label"]["comments"]
                                if x["comment_id"] == c["comment_id"]
                            ),
                            None,
                        ),
                    }
                    for c in comments
                    if c["video_id"] == vid
                ],
            }
        )
    return {
        "version": VERSION,
        "batch": batch,
        "plan": plan,
        "items": items,
        "taxonomy": config("hybrid"),
        "generated_at": now(),
    }


def write_html(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    base = ROOT / "apps/hybrid-review"
    html = (
        (base / "template.html")
        .read_text()
        .replace("/* STYLE */", (base / "style.css").read_text())
        .replace("/* SCRIPT */", (base / "app.js").read_text())
    )
    html = html.replace(
        "/* DATA */", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    )
    path.write_text(html)
    (path.parent / "hybrid-review-data.json").write_text(
        json.dumps(data, ensure_ascii=False)
    )
    return {
        "videos": len(data["items"]),
        "comments": sum(len(i["comments"]) for i in data["items"]),
        "path": str(path),
    }


def validate_review(item, row):
    if item.get("version") != VERSION or item.get("queue_hash") != row.get(
        "payload_hash", digest(row["payload"])
    ):
        raise ValueError("Review version/hash does not match immutable source")
    if (
        not isinstance(item.get("reviewer"), str)
        or not item["reviewer"].strip()
        or not item.get("reviewed_at")
    ):
        raise ValueError("Reviewer and review timestamp required")
    if item.get("basis") not in {"english_transcript", "watched_video"}:
        raise ValueError("Evidence basis required")
    label = row["payload"]["label"]
    if item.get("item_type") == "hybrid_video":
        expected = video_values(label)
    elif item.get("item_type") == "hybrid_comment":
        c = next(
            (c for c in label["comments"] if c["comment_id"] == item.get("comment_id")),
            None,
        )
        if c is None:
            raise ValueError("Unknown comment")
        expected = {k: c[k] for k in COMMENT_FIELDS}
    else:
        raise ValueError("Unknown hybrid review type")
    human, decisions = item.get("human_label", {}), item.get("decisions", {})
    if set(human) != set(expected) or set(decisions) != set(expected):
        raise ValueError("Every classification needs an explicit decision")
    for k in expected:
        if decisions[k] not in {"agree", "disagree"}:
            raise ValueError("Unconfirmed classification")
        if decisions[k] == "agree" and human[k] != expected[k]:
            raise ValueError("Agreement must preserve model label")
    cfg = config("hybrid")
    if item["item_type"] == "hybrid_comment":
        if (
            human["alignment"] not in cfg["alignment"]
            or human["response_focus"] not in cfg["response_focus"]
            or human["sentiment"] not in cfg["sentiment"]
            or not isinstance(human["sentiment_target"], str)
            or not isinstance(human["stance_target"], str)
        ):
            raise ValueError("Invalid comment labels")
        if human["response_focus"] in {
            "speaker",
            "presentation",
            "unrelated",
        } and human["alignment"] in {"supports", "opposes", "mixed"}:
            raise ValueError(
                "Speaker/presentation-only praise is not main-message agreement"
            )
        if (
            human["alignment"] in {"supports", "opposes", "mixed"}
            and not human["stance_target"].strip()
        ):
            raise ValueError(
                "Specify the video content the comment supports or opposes"
            )
    else:
        if any(
            not isinstance(human["reference:" + k], str)
            or not human["reference:" + k].strip()
            for k in REFERENCE_FIELDS
        ):
            raise ValueError(
                "Complete speaker, main message, target and speaker sentiment"
            )
        if human["reference:speaker_sentiment"] not in cfg["sentiment"]:
            raise ValueError("Invalid speaker sentiment")
        if human["relevance"] not in cfg["relevance"]:
            raise ValueError("Invalid video relevance")
        if not isinstance(human["topics"], list) or any(
            x not in cfg["topics"] for x in human["topics"]
        ):
            raise ValueError("Invalid topic")
        if len(human["topics"]) != len(set(human["topics"])):
            raise ValueError("Duplicate topic")
        if human["relevance"] != "related" and (human["topics"] or human["roles"]):
            raise ValueError(
                "Out-of-scope/unclear videos cannot have study topics/roles"
            )
        if human["relevance"] == "related" and not human["topics"]:
            raise ValueError("Relevant videos require a topic")
        if not isinstance(human["roles"], list):
            raise ValueError("Roles must be an array")
        codes = {c["iso2"] for c in config("countries")["countries"]} | {"EU", "OTHER"}
        for role in human["roles"]:
            if (
                not isinstance(role, dict)
                or role.get("role") not in cfg["roles"]
                or role.get("entity_code") not in codes
                or not str(role.get("entity", "")).strip()
            ):
                raise ValueError("Invalid entity role")
        for k in EXECUTION:
            value = human["execution:" + k]
            if value not in cfg["execution_status"] + ["absent_after_watching"]:
                raise ValueError("Invalid execution label")
            if (value == "not_applicable") == (human["relevance"] == "related"):
                raise ValueError("Execution applies only to security-related videos")
            if value == "absent_after_watching" and item["basis"] != "watched_video":
                raise ValueError("Audiovisual judgment requires watching the video")
    return item


def import_reviews(store, items):
    known = {r["id"]: r for r in labels(store)}
    prepared = []
    for item in items:
        row = known.get(item.get("queue_record_id"))
        if row is None:
            raise ValueError("Unknown or expired classification")
        validate_review(item, row)
        # Enforce the current evidence gate even if an old packet is imported.
        if row["video_id"] not in retained_inputs(store, row["batch_id"])[0]:
            raise ValueError("No retained English transcript")
        p = dict(
            item,
            review_status="complete",
            hybrid_version=VERSION,
            source_video_id=row["video_id"],
        )
        prepared.append(
            (
                row["batch_id"],
                record(
                    "human_validation",
                    row["batch_id"],
                    "hybrid-review:" + digest(p),
                    p,
                    row["video_id"],
                ),
            )
        )
    # Validate every item before writing any item.
    for batch in sorted({b for b, _ in prepared}):
        store.write(batch, [r for b, r in prepared if b == batch])
    return {"imported": len(prepared)}
