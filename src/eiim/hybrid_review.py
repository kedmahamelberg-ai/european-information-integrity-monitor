"""Private review packets and strict imports for the transcript-based taxonomy."""

import json
from pathlib import Path
from .core import ROOT, config, digest, now
from .hybrid import VERSION, retained_inputs, labels, latest_labels
from .review_sampling import sample_plan, assignment, linked_comment_plan
from .storage import record
from .engagement import engagement

VIDEO_FIELDS = ["relevance", "topics", "roles"]
EXECUTION = config("hybrid")["execution"]
REFERENCE_FIELDS = ["speaker", "summary", "target", "speaker_sentiment"]
LEGACY_COMMENT_FIELDS = [
    "response_focus",
    "alignment",
    "stance_target",
    "sentiment",
    "sentiment_target",
]
COMMENT_FIELDS = ["viewpoint_ids", *LEGACY_COMMENT_FIELDS]


def review_viewpoints(label):
    return [
        {k: viewpoint[k] for k in [
            "viewpoint_id", "speaker", "summary", "target", "speaker_sentiment"
        ]}
        for viewpoint in label.get("viewpoints", [])
    ]


def comment_fields(label):
    return COMMENT_FIELDS if "viewpoints" in label else LEGACY_COMMENT_FIELDS


def video_values(label, version=None):
    values = {
        **{k: label[k] for k in VIDEO_FIELDS},
        **{"execution:" + e["category"]: e["status"] for e in label["execution"]},
    }
    if "viewpoints" in label:
        values.update(
            viewpoint_structure=label["viewpoint_structure"],
            viewpoints=review_viewpoints(label),
        )
    else:
        values.update(
            {"reference:" + k: label["content_reference"][k] for k in REFERENCE_FIELDS}
        )
    return values


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


def packet(store, batch, plan_override=None):
    videos, comments, translations, _ = retained_inputs(store, batch)
    from .calibration import current_reviews

    saved_reviews = current_reviews(store, batch)
    current = [r for r in latest_labels(labels(store, batch)) if r["video_id"] in videos]
    population = getattr(store, "review_population", None)
    available_comments = {c["comment_id"] for c in comments
                          if translations.get(c["comment_id"], {}).get("text_english")}
    if population is not None:
        comments_by_video = population["video_comments"]
        video_ids = population["video_ids"]
    else:
        video_ids = [r["video_id"] for r in current]
        comments_by_video = {
            r["video_id"]: [
                c["comment_id"]
                for c in r["payload"]["label"]["comments"]
                if c["comment_id"] in available_comments
            ]
            for r in current
        }
    if plan_override is None:
        plan = sample_plan(
            batch, video_ids, comments_by_video=comments_by_video
        )
    else:
        plan = dict(plan_override)
        selected = plan.get("selected_video_ids")
        if (
            plan.get("batch") != batch
            or not isinstance(selected, list)
            or len(selected) != len(set(selected))
            or plan.get("target") != len(selected)
            or any(not isinstance(vid, str) or vid not in video_ids for vid in selected)
        ):
            raise ValueError("Invalid private review selection plan")
    comment_audit = linked_comment_plan(
        batch,
        plan,
        comments_by_video,
        policy={"version": plan["policy_version"]},
    )
    selected_comments = set(comment_audit["selected_comment_ids"])
    items = []
    for row in latest_labels(labels(store, batch)):
        vid, p = row["video_id"], row["payload"]
        if vid not in videos or vid not in plan["selected_video_ids"]:
            continue
        source, access = videos[vid]
        ai_comments = {c["comment_id"]: c for c in p["label"]["comments"]}
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
                "reviewer_context": p.get("reviewer_context"),
                "model_values": video_values(p["label"]),
                "version": p.get("hybrid_version", VERSION),
                "comment_fields": comment_fields(p["label"]),
                "model": p["model_version"],
                "confirmed_review": saved_reviews.get((row["id"], None)),
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
                        "review_selected": True,
                        "translation": translations.get(c["comment_id"], {}),
                        "confirmed_review": saved_reviews.get(
                            (row["id"], c["comment_id"])
                        ),
                        "prior_reviews": [
                            r["payload"]
                            for r in store.read("human_validation", batch)
                            if not r.get("purged_at")
                            and r["payload"].get("comment_id") == c["comment_id"]
                            and r["payload"].get("version") != VERSION
                        ],
                        "ai": ai_comments[c["comment_id"]],
                    }
                    for c in comments
                    if c["video_id"] == vid
                    and c["comment_id"] in selected_comments
                    and c["comment_id"] in ai_comments
                ],
            }
        )
    return {
        "version": VERSION,
        "batch": batch,
        "plan": plan,
        "comment_plan": comment_audit,
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
    source_version = row["payload"].get("hybrid_version", VERSION)
    if (
        source_version not in {VERSION, "hybrid-framing-1.5", "hybrid-framing-1.4", "hybrid-framing-1.3"}
        or item.get("version") != source_version
        or item.get("queue_hash") != row.get("payload_hash", digest(row["payload"]))
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
        expected = video_values(label, source_version)
    elif item.get("item_type") == "hybrid_comment":
        c = next(
            (c for c in label["comments"] if c["comment_id"] == item.get("comment_id")),
            None,
        )
        if c is None:
            raise ValueError("Unknown comment")
        expected = {k: c[k] for k in comment_fields(label)}
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
        if "viewpoints" in label:
            known = {v["viewpoint_id"] for v in label["viewpoints"]}
            selected = human["viewpoint_ids"]
            if (
                not isinstance(selected, list)
                or len(selected) != len(set(selected))
                or any(v not in known for v in selected)
            ):
                raise ValueError("Choose only known viewpoint IDs")
            if human["alignment"] in {"supports", "opposes", "mixed"} and not selected:
                raise ValueError("Substantive alignment requires a viewpoint")
    else:
        if "viewpoints" in label:
            viewpoints = human["viewpoints"]
            structure = human["viewpoint_structure"]
            if structure not in cfg["viewpoint_structure"] or not isinstance(viewpoints, list):
                raise ValueError("Invalid viewpoint structure")
            if structure == "single_viewpoint" and len(viewpoints) != 1:
                raise ValueError("Single-viewpoint videos require one viewpoint")
            if structure == "multiple_viewpoints" and len(viewpoints) < 2:
                raise ValueError("Debates require at least two viewpoints")
            ids = [v.get("viewpoint_id") for v in viewpoints if isinstance(v, dict)]
            if len(ids) != len(viewpoints) or len(ids) != len(set(ids)):
                raise ValueError("Viewpoint IDs must be unique")
            for viewpoint in viewpoints:
                if (
                    not all(str(viewpoint.get(k, "")).strip() for k in ["viewpoint_id", "speaker", "summary", "target"])
                    or viewpoint.get("speaker_sentiment") not in cfg["sentiment"]
                ):
                    raise ValueError("Complete every viewpoint attribution")
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
        for k in [e["category"] for e in label["execution"]]:
            value = human["execution:" + k]
            if value not in cfg["execution_status"] + ["absent_after_watching"]:
                raise ValueError("Invalid execution label")
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
            hybrid_version=item["version"],
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
