"""Private, credential-free human review packets; never part of Pages output."""

import json
from pathlib import Path
from .core import ROOT, config, digest, now
from .storage import record
from .language_access import access_records, video_access


def model_values(item):
    m = item["model_label"]
    if item["item_type"] == "video":
        return {
            **{k: m[k] for k in ("othering", "aversion", "moralization")},
            "narratives": m.get("narratives", []),
            "targets": [
                t["target_name"] if isinstance(t, dict) else t
                for t in m.get("targets", [])
            ],
            "countries": m.get("countries", []),
        }
    if item["item_type"] == "comment_cluster":
        return {
            "coherent": True,
            "off_topic": m["topic_similarity"]
            < config("amplification")["off_topic_similarity"],
            "different_narrative": not m["narrative_alignment"],
        }
    return {"news_relevance": bool(m["news_relevance"])}


def prepare_review_items(store, batch=None):
    """Offer every classified sampled video, even before comment analytics finish."""
    queues = store.read("human_validation", batch)
    candidates = {
        (r["batch_id"], r["video_id"]): r["payload"]
        for r in store.read("candidate_videos", batch)
        if not r.get("purged_at")
    }
    sidecars = store.read("pipeline_runs", batch)
    access = access_records(sidecars)
    translations = {
        (r["batch_id"], r["payload"]["comment_translation_id"]): r["payload"]
        for r in sidecars
        if not r.get("purged_at") and "comment_translation_id" in r["payload"]
    }
    known = {
        (
            q["batch_id"],
            q["payload"]["item_type"],
            q.get("video_id")
            or q["payload"].get("model_label", {}).get("video_id")
            or q["payload"]["item_id"].split(":")[-1],
        )
        for q in queues
        if not q.get("purged_at")
    }
    samples = {
        (r["batch_id"], r["video_id"]): r["payload"]
        for r in store.read("sampled_videos", batch)
        if not r.get("purged_at")
    }
    additions = []
    for r in store.read("video_classifications", batch):
        source = candidates.get(
            (r["batch_id"], r["video_id"]), {"video_id": r["video_id"]}
        )
        if not video_access(source, r["batch_id"], access)["eligible"]:
            continue
        if r.get("purged_at") or (r["batch_id"], "video", r["video_id"]) in known:
            continue
        s = samples.get((r["batch_id"], r["video_id"]))
        if not s or not s.get("selected_for_sample"):
            continue
        m = r["payload"]
        model = {
            **m,
            "id": r["id"],
            "narratives": [m["primary_narrative"], *m["secondary_narratives"]],
            "tier": s["tier"],
            "language": s.get("language", "und"),
            "sampling_country": s.get("sampling_country"),
        }
        q = {
            "item_id": r["id"],
            "item_type": "video",
            "model_label": model,
            "human_label": None,
            "adjudicated_label": None,
            "review_status": "pending",
            "qa_strata": ["available_sampled_classification"],
            "classifier_version": m["classifier_version"],
        }
        additions.append(
            record(
                "human_validation",
                r["batch_id"],
                r["batch_id"] + ":review-video:" + r["video_id"],
                q,
                r["video_id"],
            )
        )
    for b in sorted({r["record"]["batch_id"] for r in additions}):
        store.write(b, [r for r in additions if r["record"]["batch_id"] == b])
    queues += [r["record"] for r in additions]
    candidates = {
        (r["batch_id"], r["video_id"]): r["payload"]
        for r in store.read("candidate_videos", batch)
        if not r.get("purged_at")
    }
    comments = {
        r["id"]: r["payload"]
        for r in store.read("comments", batch)
        if not r.get("purged_at")
    }
    finished = {
        r["payload"].get("source_queue_record_id")
        for r in queues
        if r["payload"].get("review_status") == "complete"
    }
    finished_items = {
        (
            r["payload"]["item_type"],
            r["payload"]["item_id"],
            r["payload"].get("classifier_version"),
        )
        for r in queues
        if r["payload"].get("review_status") == "complete"
    }
    from .reclassification import VERSION

    def queue_video(r):
        q = r["payload"]
        return (
            r.get("video_id")
            or q["model_label"].get("video_id")
            or q["item_id"].split(":")[-1]
        )

    # Prefer a candidate revision only when it actually exists for this source.
    # Old labels and confirmed reviews remain immutable and visible as context.
    preferred = {}
    previous_reviews = {}
    for r in queues:
        q = r["payload"]
        key = (r["batch_id"], queue_video(r))
        if r.get("purged_at") or q.get("item_type") != "video":
            continue
        if q.get("review_status") == "complete":
            previous_reviews.setdefault(key, []).append(q)
        if (
            q.get("classifier_version") == VERSION
            and q.get("review_status") == "pending"
        ):
            old = preferred.get(key)
            if old is None or q["model_label"].get(
                "classification_timestamp", ""
            ) > old["payload"]["model_label"].get("classification_timestamp", ""):
                preferred[key] = r
    items = []
    seen = set()
    for r in queues:
        q = r["payload"]
        newer = preferred.get((r["batch_id"], queue_video(r)))
        if (
            q["model_label"].get("validation_status")
            == "candidate_awaiting_human_validation"
            and q.get("classifier_version") != VERSION
        ):
            continue
        if q["item_type"] == "video" and newer and newer["id"] != r["id"]:
            continue
        if (
            r.get("purged_at")
            or q.get("review_status") != "pending"
            or r["id"] in finished
            or (q["item_type"], q["item_id"], q.get("classifier_version"))
            in finished_items
        ):
            continue
        vid = (
            r.get("video_id")
            or q["model_label"].get("video_id")
            or q["item_id"].split(":")[-1]
        )
        identity = (r["batch_id"], q["item_type"], q["item_id"])
        if identity in seen:
            continue
        seen.add(identity)
        source = candidates.get((r["batch_id"], vid), {})
        eligibility = video_access(dict(source, video_id=vid), r["batch_id"], access)
        if not eligibility["eligible"]:
            continue
        source_comments = []
        for cid in q["model_label"].get("comment_ids", []):
            c = comments.get(r["batch_id"] + ":" + cid)
            translated = translations.get((r["batch_id"], cid))
            if c and translated and translated.get("text_english"):
                source_comments.append(
                    {
                        "text": c.get("text_original", ""),
                        "text_english": translated["text_english"],
                        "original_language": c.get(
                            "original_language", c.get("language", "und")
                        ),
                        "translation_status": translated["translation_status"],
                        "translation_detected_language": translated.get(
                            "translation_detected_language"
                        ),
                        "published_at": c.get("published_at"),
                    }
                )
        if q["item_type"] == "comment_cluster" and len(source_comments) != len(
            q["model_label"].get("comment_ids", [])
        ):
            continue
        fields = [
            "video_id",
            "title",
            "description",
            "channel",
            "published_at",
            "retrieved_at",
        ]
        item = {
            "queue_record_id": r["id"],
            "queue_hash": digest(q),
            "batch": r["batch_id"],
            **q,
            "source_observation": {k: source.get(k) for k in fields},
            "english_access": eligibility,
            "source_comments": source_comments,
            "score_max": q["model_label"].get("score_max", 4),
            "previous_reviews": [
                {
                    k: p.get(k)
                    for k in [
                        "classifier_version",
                        "score_max",
                        "human_label",
                        "reviewer",
                        "reviewed_at",
                        "review_evidence_basis",
                        "review_evidence_note",
                    ]
                }
                for p in previous_reviews.get((r["batch_id"], vid), [])
                if p.get("classifier_version") != q.get("classifier_version")
            ],
        }
        item["ai_values"] = model_values(item)
        items.append(item)
    # Round-robin country/tier/language cells so early review is not all one stratum.
    from collections import defaultdict

    groups = defaultdict(list)
    for item in items:
        m = item["model_label"]
        groups[
            (
                item["item_type"],
                m.get("sampling_country", ""),
                m.get("tier", ""),
                m.get("language", ""),
            )
        ].append(item)
    for group in groups.values():
        group.sort(key=lambda x: digest(x["queue_record_id"]))
    ordered = []
    while any(groups.values()):
        for key in sorted(groups):
            if groups[key]:
                ordered.append(groups[key].pop(0))
    return ordered


def write_review_html(items, output, progress=None):
    output = Path(output)
    if (
        ROOT / "apps/dashboard" in output.resolve().parents
        or ROOT / "build" in output.resolve().parents
    ):
        raise ValueError("Review packets must stay outside public website directories")
    payload = {
        "generated_at": now(),
        "items": items,
        "progress": progress or {},
        "narratives": config("narratives")["labels"],
        "countries": [
            {"iso2": c["iso2"], "name": c["country_name"]}
            for c in config("countries")["countries"]
        ],
    }
    serialized = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    html = (ROOT / "apps/review/template.html").read_text()
    html = html.replace(
        "/* REVIEW_STYLE */", (ROOT / "apps/review/style.css").read_text()
    )
    html = html.replace(
        "/* REVIEW_SCRIPT */", (ROOT / "apps/review/app.js").read_text()
    )
    html = html.replace("__REVIEW_PAYLOAD__", serialized)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".tmp")
    temp.write_text(html)
    temp.replace(output)
    data_path = output.with_name("review-data.json")
    temp = data_path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False))
    temp.replace(data_path)
    return {"private_html": str(output), "items": len(items)}


def validate_assisted_review(item, queue):
    """Validate deliberate field decisions; never treat an untouched AI label as review."""
    from datetime import datetime

    if item.get("queue_hash") != digest(queue):
        raise ValueError("Review packet no longer matches its immutable queue record")
    if item.get("review_method") != "ai_assisted_confirmation":
        raise ValueError("Review method must describe AI-assisted confirmation")
    if queue["model_label"].get("evidence_scope") and item.get(
        "review_evidence_basis"
    ) not in {"metadata_only", "metadata_and_english_transcript", "watched_video"}:
        raise ValueError("Record the evidence basis of the candidate review")
    values = model_values(queue)
    decisions = item.get("review_decisions", {})
    human_label = item["human_label"]
    if not isinstance(decisions, dict) or set(decisions) != set(values):
        raise ValueError("Explicit decision required for every classification")

    def canonical(v):
        return sorted(v) if isinstance(v, list) else v

    for key, ai in values.items():
        value = human_label.get(key)
        if isinstance(ai, list) and (
            not isinstance(value, list) or any(not isinstance(x, str) for x in value)
        ):
            raise ValueError("List labels must contain strings")
        equal = canonical(value) == canonical(ai)
        if decisions[key] == "agree" and not equal:
            raise ValueError("Agreed label differs from the AI label")
        if decisions[key] == "disagree" and equal:
            raise ValueError("Disagreement needs a corrected label")
        if decisions[key] not in ("agree", "disagree"):
            raise ValueError("Unconfirmed label")
    if "countries" in human_label and any(
        x not in {c["iso2"] for c in config("countries")["countries"]}
        for x in human_label["countries"]
    ):
        raise ValueError("Unknown country code")
    if "narratives" in human_label and (
        not human_label["narratives"]
        or any(
            x not in config("narratives")["labels"] for x in human_label["narratives"]
        )
    ):
        raise ValueError("Unknown narrative label")
    timestamp = datetime.fromisoformat(item["reviewed_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Review timestamp needs a timezone")
