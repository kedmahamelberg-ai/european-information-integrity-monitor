"""Private, credential-free human review packets; never part of Pages output."""

import json
from pathlib import Path
from .core import ROOT, config, digest, now
from .storage import record


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
    items = []
    seen = set()
    for r in queues:
        q = r["payload"]
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
            "source_comments": [
                {
                    "text": comments[key].get("text_original", ""),
                    "published_at": comments[key].get("published_at"),
                }
                for cid in q["model_label"].get("comment_ids", [])
                if (key := r["batch_id"] + ":" + cid) in comments
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
