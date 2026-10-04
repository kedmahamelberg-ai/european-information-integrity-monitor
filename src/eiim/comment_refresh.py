"""Append a corrected comment sample without replacing frozen observations."""

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from .core import config, digest, now, coherent_clusters, injection
from .pipeline import Pipeline
from .services import YouTube, LocalModel, Classifier, BudgetExhausted
from .storage import record


def refresh_comments(store, batch, youtube=None, local=None, classifier=None):
    batches = store.read("weekly_batches", batch)
    if not batches:
        raise ValueError("An existing retained batch is required")
    window = batches[0]["payload"]
    collected = datetime.fromisoformat(
        window["collection_timestamp"].replace("Z", "+00:00")
    )
    if collected < datetime.now(timezone.utc) - timedelta(
        days=config("retention")["raw_retention_days"]
    ):
        raise ValueError("The batch is outside raw-data retention")
    if any(r.get("purged_at") for r in store.read("candidate_videos", batch)):
        raise ValueError("Cannot refresh purged source observations")
    pipe = Pipeline(store, collected, youtube, local, classifier)
    pipe.id, pipe.window = batch, window
    pipe.ledger.batch = batch
    pipe.yt = youtube or YouTube(store, batch, pipe.ledger)
    pipe.local = local or LocalModel(pipe.ledger)
    pipe.classifier = classifier or Classifier(store, batch, pipe.ledger)
    before = len(pipe.values("comments"))
    status = "complete"
    try:
        pipe.comments(refresh_policy=True, mark_complete=False)
        pipe.classification(classify_sources=False, mark_complete=False)
    except BudgetExhausted:
        status = "pending_budget"
    cluster_count = add_review_clusters(pipe)
    comments = pipe.values("comments")
    labels = pipe.cached("comment_classifications", "comment_id")
    pending = sum(c["comment_id"] not in labels for c in comments)
    if pending and status == "complete":
        status = "partial"
    report = {
        "batch": batch,
        "status": status,
        "minimum_available_comments": pipe.cfg["minimum_available_comments"],
        "sampling_version": pipe.cfg["version"],
        "comments_retained": len(comments),
        "new_comments": len(comments) - before,
        "videos_with_comments": len({c["video_id"] for c in comments}),
        "classified_comments": sum(c["comment_id"] in labels for c in comments),
        "pending_classifications": pending,
        "new_review_clusters": cluster_count,
        "frozen_snapshots_preserved": True,
        "generated_at": now(),
    }
    store.write(
        batch,
        [
            record(
                "pipeline_runs",
                batch,
                batch + ":comment-refresh:" + digest(report),
                {"comment_refresh_report": report},
            )
        ],
    )
    return report


def add_review_clusters(pipe):
    """Offer new fully translated clusters; preserve existing cluster queues."""
    candidates = pipe.cached("candidate_videos", "video_id")
    labels = pipe.cached("video_classifications", "video_id")
    from .reclassification import VERSION

    for p in pipe.values("pipeline_runs"):
        if p.get("classifier_version") == VERSION and "reclassification_video_id" in p:
            labels[p["reclassification_video_id"]] = p
    comment_labels = pipe.cached("comment_classifications", "comment_id")
    embeddings = pipe.cached("comment_embeddings_metadata", "comment_id")
    translated = {
        p["comment_translation_id"]
        for p in pipe.values("pipeline_runs")
        if "comment_translation_id" in p
    }
    existing_videos = {p["video_id"] for p in pipe.values("comment_clusters")}
    grouped = defaultdict(list)
    active = {s["video_id"] for s in pipe.active_samples()}
    for c in pipe.values("comments"):
        if c["video_id"] in active:
            grouped[c["video_id"]].append(c)
    cfg = config("amplification")
    rows = []
    for vid, comments in sorted(grouped.items()):
        if vid in existing_videos or vid not in labels:
            continue
        cs = sorted(comments, key=lambda c: c["comment_id"])
        if any(
            c["comment_id"] not in comment_labels
            or c["comment_id"] not in embeddings
            or c["comment_id"] not in translated
            for c in cs
        ):
            continue
        vectors = [embeddings[c["comment_id"]]["vector"] for c in cs]
        groups = coherent_clusters(
            vectors, cfg["coherent_similarity"], cfg["cluster_min_size"]
        )
        if not groups:
            continue
        v, label = candidates[vid], labels[vid]
        source = pipe.local.embed([v["title"] + "\n" + v["description"]])[0]
        cluster_labels = {
            i: [
                Counter(
                    comment_labels[cs[j]["comment_id"]]["primary_narrative"] for j in g
                ).most_common(1)[0][0]
            ]
            for i, g in enumerate(groups)
        }
        result = injection(
            groups,
            source,
            vectors,
            [label["primary_narrative"], *label["secondary_narratives"]],
            cluster_labels,
        )
        for g in result["clusters"]:
            ids = [cs[j]["comment_id"] for j in g["members"]]
            cid = vid + ":comments-min-2:" + digest(ids)[:16]
            payload = {
                "id": cid,
                "video_id": vid,
                **g,
                "comment_ids": ids,
                "sampling_version": pipe.cfg["version"],
                "minimum_available_comments": pipe.cfg["minimum_available_comments"],
            }
            rows.append(
                record("comment_clusters", pipe.id, pipe.id + ":" + cid, payload, vid)
            )
            queue = {
                "item_id": cid,
                "item_type": "comment_cluster",
                "model_label": payload,
                "human_label": None,
                "adjudicated_label": None,
                "review_status": "pending",
                "classifier_version": pipe.models["classifier_version"],
            }
            rows.append(
                record("human_validation", pipe.id, pipe.id + ":" + cid, queue, vid)
            )
    if rows:
        pipe.store.write(pipe.id, rows)
    return len(rows) // 2
