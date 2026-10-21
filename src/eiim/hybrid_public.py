"""Explicit public allowlist: counters and attributed labels, never raw discussions."""

import json
from .core import config, now
from .hybrid import VERSION, retained_inputs, labels, latest_labels
from .hybrid_review import video_values
from .review_sampling import sample_plan
from .engagement import engagement
from .language_access import access_records, video_access, caption_state, publishable_label
from .calibration import current_reviews
from collections import Counter


def _audit_progress(plan, rows, reviews):
    """Count validated work without losing legacy reviews after policy changes."""
    reviewed = {
        row["id"]: reviews[row["id"]]
        for row in rows.values()
        if row["id"] in reviews
    }
    assigned = [
        review
        for review in reviewed.values()
        if review.get("review_assignment", {}).get("selected")
    ]
    if assigned:
        target = max(
            review["review_assignment"].get("target", plan["target"])
            for review in assigned
        )
        # A growing current sample increases the target when prior reviewed
        # videos remain in that sample. An unrelated legacy assignment keeps
        # its original target rather than inheriting a different plan.
        if any(
            video_id in plan.get("selected_video_ids", ()) and row["id"] in reviewed
            for video_id, row in rows.items()
        ):
            target = max(target, plan["target"])
        completed = min(target, len(assigned))
    else:
        # Older exports did not retain their immutable assignment metadata.
        # Every validated video review still represents completed human work.
        target = plan["target"]
        completed = min(target, len(reviewed))
    return target, completed


def export_public(store, path):
    output = {
        "version": VERSION,
        "as_of": now(),
        "mode": "live",
        "videos": [],
        "inventory": [],
        "caption_health": {},
        "caption_recovery": [],
        "learning": "Human corrections guide prompts and retained calibration examples; this is not model fine-tuning.",
        "batches": [],
        "status": "human_review_pending",
        "collection": {
            "sampled_videos": 0,
            "transcript_eligible": 0,
            "classified_videos": 0,
            "reviewed_videos": 0,
            "retained_comments": 0,
            "classified_comments": 0,
            "all_retained_comments": 0,
            "reviewed_comments": 0,
        },
        "role_labels": config("hybrid")["role_labels"],
        "topic_labels": config("hybrid")["topic_labels"],
    }
    caption_health = Counter()
    retained_batches = store.read("weekly_batches")
    labels_by_batch = {}
    validated = {}
    reviews = {}
    # Read labels and reviews per retained batch.  A previous global scan sent
    # every transcript-bearing pipeline record once here and then sent the same
    # records again in retained_inputs below.  Batch-scoped reads are reused by
    # Store's run cache and keep publication egress proportional to retained data.
    for b in retained_batches:
        batch = b["id"]
        labels_by_batch[batch] = {
            r["id"]: r for r in latest_labels(labels(store, batch))
        }
        batch_reviews = current_reviews(store, batch)
        validated.update(batch_reviews)
        for (queue_record_id, comment_id), review in batch_reviews.items():
            if comment_id is None and review.get("item_type") == "hybrid_video":
                reviews[queue_record_id] = review
    for b in retained_batches:
        batch = b["id"]
        videos, comments, _, _ = retained_inputs(store, batch)
        sampled = {
            r["video_id"]
            for r in store.read("sampled_videos", batch)
            if not r.get("purged_at") and r["payload"].get("selected_for_sample")
        }
        if not sampled:
            continue
        candidates = {r["video_id"]: r["payload"] for r in store.read("candidate_videos", batch) if not r.get("purged_at")}
        accesses = access_records(store.read("pipeline_runs", batch))
        recovery = [r["payload"] for r in store.read("pipeline_runs", batch)
                    if not r.get("purged_at") and "caption_recovery_report" in r["payload"]]
        if recovery:
            latest = max(recovery, key=lambda p: p["checked_at"])
            health = latest["caption_recovery_report"]
            output["caption_recovery"].append({
                "batch": batch, "checked_at": latest["checked_at"],
                "direct_reader_blocked": health.get("direct_reader_blocked"),
                "provider_configured": health.get("fallback", {}).get("configured", False),
                "audio_configured": health.get("audio", {}).get("configured", False),
                "audio_saved": health.get("audio", {}).get("saved_transcripts", 0),
                "audio_stopped": health.get("audio", {}).get("stopped"),
            })
        for sampled_row in store.read("sampled_videos", batch):
            vid = sampled_row["video_id"]
            if vid not in sampled or sampled_row.get("purged_at"):
                continue
            source = dict(sampled_row["payload"], **candidates.get(vid, {}))
            source["video_id"] = vid
            access = video_access(source, batch, accesses)
            reason = caption_state(access)
            caption_health[reason] += 1
            output["inventory"].append({"id": vid, "batch": batch, "title": source.get("title", ""), "channel": source.get("channel", ""), "countries": source.get("countries", []), "published_at": source.get("published_at"), "original_language": access.get("original_language", "und"), "caption_state": reason, "engagement": engagement(source)})
        rows = {
            r["video_id"]: r
            for r in labels_by_batch[batch].values()
            if r["video_id"] in videos
            and publishable_label(r)
        }
        comments_by_video = {
            vid: [
                item["comment_id"]
                for item in row["payload"]["label"].get("comments", [])
            ]
            for vid, row in rows.items()
        }
        plan = sample_plan(batch, videos, comments_by_video=comments_by_video)
        audit_target, audit_completed = _audit_progress(plan, rows, reviews)
        audit_complete = (
            bool(audit_target)
            and audit_completed >= audit_target
            and len(rows) == len(videos)
        )
        output["batches"].append(
            {
                "id": batch,
                "window_start": b["payload"].get("window_start"),
                "window_end": b["payload"].get("window_end"),
                "audit_target": audit_target,
                "audit_completed": audit_completed,
                "audit_complete": audit_complete,
            }
        )
        c = output["collection"]
        c["all_retained_comments"] += sum(not r.get("purged_at") for r in store.read("comments", batch))
        c["sampled_videos"] += len(sampled)
        c["transcript_eligible"] += len(videos)
        c["classified_videos"] += len(rows)
        c["retained_comments"] += len(comments)
        c["classified_comments"] += sum(
            len(r["payload"]["label"]["comments"]) for r in rows.values()
        )
        for vid, (source, access) in videos.items():
            row = rows.get(vid)
            review = reviews.get(row["id"]) if row else None
            human = (
                review["human_label"]
                if review
                else (
                    video_values(row["payload"]["label"])
                    if row
                    else None
                )
            )
            c["reviewed_videos"] += bool(review)
            # Human attribution/rationale/quotes and comment text never leave the private packet.
            public_label = (
                None
                if human is None
                else {
                    "relevance": human["relevance"],
                    "topics": human["topics"],
                    "roles": [
                        {k: r[k] for k in ["entity", "entity_code", "role"]}
                        for r in human["roles"]
                    ],
                    "execution": {
                        k: human["execution:" + k]
                        for k in config("hybrid")["execution"]
                    },
                }
            )
            response = comment_summary(row, validated)
            c["reviewed_comments"] += response["human_reviewed"]
            output["videos"].append(
                {
                    "id": vid,
                    "batch": batch,
                    "title": source.get("title", ""),
                    "channel": source.get("channel", ""),
                    "countries": source.get("countries", []),
                    "published_at": source.get("published_at"),
                    "tier": source.get("tier"),
                    "original_language": access["original_language"],
                    "caption_status": access.get("status"),
                    "transcript_method": access.get("caption_provider", "youtube_captions"),
                    "transcript_translation": access.get("caption_translation", "none"),
                    "responses": response,
                    "engagement": engagement(source),
                    "retained_comments": sum(x["video_id"] == vid for x in comments),
                    "classified_comments": (
                        len(row["payload"]["label"]["comments"]) if row else 0
                    ),
                    "classification_status": (
                        "human_reviewed"
                        if review
                        else (
                            "ai_coded_sample_audited"
                            if audit_complete and row
                            else (
                                "ai_provisional"
                                if row
                                else "awaiting_classification"
                            )
                        )
                    ),
                    "label": public_label,
                    "model": row["payload"]["model_version"] if row else None,
                    "transcript_truncated": (
                        row["payload"]["transcript_truncated"] if row else None
                    ),
                }
            )
    output["caption_health"] = dict(caption_health)
    output["collection"]["awaiting_transcript"] = (
        output["collection"]["sampled_videos"]
        - output["collection"]["transcript_eligible"]
    )
    output["status"] = (
        "human_review_complete"
        if output["batches"] and all(b["audit_complete"] for b in output["batches"])
        else "human_review_pending"
    )
    output["classification_status"] = (
        "awaiting_transcripts" if output["collection"]["awaiting_transcript"] else
        "awaiting_classification" if output["collection"]["classified_videos"] < output["collection"]["transcript_eligible"] else
        "complete"
    )
    output["human_review_required_for_classification"] = False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    return output["collection"]


def comment_summary(row, reviews):
    """Counts only: never publish comment text, usernames or quoted evidence."""
    counts = {k: Counter() for k in ["alignment", "sentiment", "response_focus"]}
    reviewed = 0
    joint = {}
    comments = row["payload"]["label"].get("comments", []) if row else []
    for ai in comments:
        review = reviews.get((row["id"], ai["comment_id"]))
        value = review["human_label"] if review else ai
        reviewed += bool(review)
        alignment = value.get("alignment", "unclear")
        sentiment = value.get("sentiment", "unclear")
        joint.setdefault(alignment, Counter())[sentiment] += 1
        for field in counts:
            counts[field][value.get(field, "unclear")] += 1
    return {**{k: dict(v) for k, v in counts.items()}, "alignment_sentiment": {k: dict(v) for k, v in joint.items()}, "total": len(comments), "human_reviewed": reviewed, "ai_only": len(comments) - reviewed}
