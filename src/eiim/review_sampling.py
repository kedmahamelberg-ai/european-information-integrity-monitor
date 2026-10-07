"""Reproducible human workload, sampled independently of model outcomes."""

from math import ceil
from .core import config, digest
from .language_access import access_records, video_access


def sample_plan(batch, video_ids, policy=None):
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
        "selection_method": "seeded hash ranking of eligible frozen sampled video IDs; independent of labels",
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


def comment_plan(batch, comment_ids, policy=None):
    """Independent 3% audit of coded, translated comments, not video clusters."""
    policy = policy or config("review_sampling")
    population = sorted(set(comment_ids))
    target = min(len(population), max(policy["routine_minimum"],
                 ceil(len(population) * policy["routine_fraction"])))
    ranked = sorted(population, key=lambda cid: (digest([policy["seed"], batch, "comment", cid]), cid))
    return {"policy_version": policy["version"], "batch": batch,
            "population": len(population), "population_hash": digest(population),
            "target": target, "fraction": policy["routine_fraction"],
            "minimum": policy["routine_minimum"], "selected_comment_ids": ranked[:target]}
