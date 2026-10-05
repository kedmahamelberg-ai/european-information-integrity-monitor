"""Auditable schema projection and retained human examples; never model training."""

import copy
from .core import digest
from .storage import record


def project_four_categories(store, batch):
    """Remove one retired field, preserving every other human decision verbatim."""
    from .hybrid import VERSION, latest_labels, retained_inputs
    from .hybrid_review import validate_review

    if VERSION != "hybrid-framing-1.4":
        raise ValueError("Projection is specific to schema 1.4")
    eligible = retained_inputs(store, batch)[0]
    originals = latest_labels(
        [
            r
            for r in store.read("pipeline_runs", batch)
            if not r.get("purged_at")
            and r["payload"].get("hybrid_version") == "hybrid-framing-1.3"
            and "label" in r["payload"]
            and r["video_id"] in eligible
        ]
    )
    existing = {r["id"] for r in store.read("pipeline_runs", batch)}
    pending, projected = [], {}
    for old in originals:
        ident = batch + ":schema-1.4:" + digest([old["id"], old["payload_hash"]])
        p = copy.deepcopy(old["payload"])
        p["hybrid_version"] = VERSION
        p["label"]["execution"] = [
            e for e in p["label"]["execution"] if e["category"] != "imagery_visual"
        ]
        p["schema_projection"] = {
            "from_record": old["id"],
            "from_hash": old["payload_hash"],
            "removed_field": "execution:imagery_visual",
            "rule": "drop-imagery-only-v1",
        }
        new = record("pipeline_runs", batch, ident, p, old["video_id"])
        projected[old["id"]] = (old, new["record"])
        if ident not in existing:
            pending.append(new)
    migrated = 0
    for review in store.read("human_validation", batch):
        p = review["payload"]
        pair = projected.get(p.get("queue_record_id"))
        if review.get("purged_at") or p.get("review_status") != "complete" or not pair:
            continue
        old, new = pair
        validate_review(p, old)
        q = copy.deepcopy(p)
        q.update(
            version=VERSION,
            hybrid_version=VERSION,
            queue_record_id=new["id"],
            queue_hash=new["payload_hash"],
        )
        q["human_label"].pop("execution:imagery_visual", None)
        q["decisions"].pop("execution:imagery_visual", None)
        q["schema_projection"] = {
            "from_review": review["id"],
            "from_hash": review["payload_hash"],
            "rule": "drop-imagery-only-v1",
            "original_version": p["version"],
        }
        validate_review(q, new)
        pending.append(
            record(
                "human_validation",
                batch,
                "hybrid-review:" + digest(q),
                q,
                new["video_id"],
            )
        )
        migrated += 1
    if pending:
        store.write(batch, pending)
    return {
        "projected_videos": len(projected),
        "preserved_reviews": migrated,
        "new_model_calls": 0,
    }


def current_reviews(store, batch=None):
    from .hybrid import labels, latest_labels
    from .hybrid_review import validate_review

    known = {r["id"]: r for r in latest_labels(labels(store, batch))}
    out = {}
    for r in sorted(
        store.read("human_validation", batch),
        key=lambda r: r["payload"].get("reviewed_at", ""),
    ):
        p = r["payload"]
        source = known.get(p.get("queue_record_id"))
        if r.get("purged_at") or p.get("review_status") != "complete" or not source:
            continue
        try:
            validate_review(p, source)
        except (ValueError, KeyError, TypeError):
            continue
        out[(source["id"], p.get("comment_id"))] = p
    return out


def calibration_examples(store, exclude_video_id=None):
    """Bounded private examples from validated retained reviews, excluding self."""
    from .hybrid import labels, retained_inputs

    known = {r["id"]: r for r in labels(store)}
    examples = {"videos": [], "comments": []}
    cache = {}
    reviews = sorted(
        current_reviews(store).values(),
        key=lambda p: sum(v == "disagree" for v in p["decisions"].values()),
        reverse=True,
    )
    for p in reviews:
        row = known[p["queue_record_id"]]
        if row["video_id"] == exclude_video_id:
            continue
        batch = row["batch_id"]
        if batch not in cache:
            cache[batch] = retained_inputs(store, batch)
        videos, comments, translations, _ = cache[batch]
        if row["video_id"] not in videos:
            continue
        cid = p.get("comment_id")
        kind = "comments" if cid else "videos"
        if len(examples[kind]) >= (6 if cid else 4):
            continue
        example = {
            "reviewer": p["reviewer"],
            "human_label": p["human_label"],
            "reference": row["payload"]["label"]["content_reference"],
            "basis": p["basis"],
        }
        if cid:
            translated = translations.get(cid, {}).get("text_english")
            if not translated:
                continue
            example["text_english"] = translated[:2000]
        else:
            source, access = videos[row["video_id"]]
            example["title"] = source["title"]
            example["transcript_excerpt"] = " ".join(
                s["text"] for s in access["transcript_english"]
            )[:2400]
        examples[kind].append(example)
    return examples
