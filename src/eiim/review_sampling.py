"""Reproducible human workload sampled as video clusters."""

from math import ceil
from .core import config, digest
from .language_access import access_records, video_access


def sample_plan(batch, video_ids, policy=None, comments_by_video=None):
    policy = policy or config("review_sampling")
    population = sorted(set(video_ids))
    calibration = batch == policy["calibration_batch"]
    requested = (
        policy["calibration_videos"]
        if calibration
        else max(
            policy["routine_minimum"],
            ceil(len(population) * policy["routine_fraction"]),
        )
    )
    ranked = sorted(
        population, key=lambda vid: (digest([policy["seed"], batch, vid]), vid)
    )
    target = min(len(population), requested)
    method = "seeded hash ranking of eligible frozen sampled video IDs; independent of labels"
    if target and comments_by_video is not None:
        with_comments = [vid for vid in population if comments_by_video.get(vid)]
        without_comments = [vid for vid in population if not comments_by_video.get(vid)]
        if with_comments and without_comments and target > 1:
            first_with = min(
                with_comments,
                key=lambda vid: (digest([policy["seed"], batch, "with-comments", vid]), vid),
            )
            first_without = min(
                without_comments,
                key=lambda vid: (digest([policy["seed"], batch, "without-comments", vid]), vid),
            )
            required = {first_with, first_without}
            selected = list(required)
            selected.extend(vid for vid in ranked if vid not in required)
            ranked = sorted(
                selected[:target],
                key=lambda vid: (digest([policy["seed"], batch, vid]), vid),
            )
            method = (
                "seeded hash ranking of eligible frozen sampled video IDs, "
                "stratified by presence of classified comments; independent of labels"
            )
        elif with_comments and target == 1:
            ranked = sorted(
                with_comments,
                key=lambda vid: (digest([policy["seed"], batch, "with-comments", vid]), vid),
            )
            method = (
                "seeded hash ranking of eligible frozen sampled video IDs with a "
                "classified comment; independent of labels"
            )
    return {
        "policy_version": policy["version"],
        "batch": batch,
        "phase": "calibration" if calibration else "routine",
        "population": len(population),
        "population_hash": digest(population),
        "target": target,
        "fraction": policy["routine_fraction"],
        "minimum": policy["routine_minimum"],
        "selected_video_ids": ranked[:target],
        "selection_method": method,
    }


def plans_for_store(store, batch=None):
    access = access_records(store.read("pipeline_runs", batch))
    candidates = {
        (r["batch_id"], r["video_id"]): r["payload"]
        for r in store.read("candidate_videos", batch)
        if not r.get("purged_at")
    }
    populations = {}
    for r in store.read("sampled_videos", batch):
        if r.get("purged_at") or not r["payload"].get("selected_for_sample"):
            continue
        b, vid = r["batch_id"], r["video_id"]
        source = dict(candidates.get((b, vid), {}), video_id=vid)
        if video_access(source, b, access)["eligible"]:
            populations.setdefault(b, []).append(vid)
    return {b: sample_plan(b, vids) for b, vids in populations.items()}


def assignment(plan, video_id):
    return {
        "policy_version": plan["policy_version"],
        "phase": plan["phase"],
        "population": plan["population"],
        "population_hash": plan["population_hash"],
        "target": plan["target"],
        "selected": video_id in plan["selected_video_ids"],
    }


def linked_comment_plan(batch, video_plan, comments_by_video, policy=None):
    """Include every classified comment attached to the sampled videos."""
    policy = policy or config("review_sampling")
    normalized = {
        vid: sorted(set(comments_by_video.get(vid, [])))
        for vid in video_plan["selected_video_ids"]
    }
    population = sorted(
        {cid for ids in comments_by_video.values() for cid in ids}
    )
    selected = sorted({cid for ids in normalized.values() for cid in ids})
    return {
        "policy_version": policy["version"],
        "batch": batch,
        "population": len(population),
        "population_hash": digest(population),
        "target": len(selected),
        "fraction": video_plan["fraction"],
        "minimum": 0,
        "selected_video_ids": video_plan["selected_video_ids"],
        "selected_comment_ids": selected,
        "selection_method": "all classified comments attached to selected video clusters",
    }
