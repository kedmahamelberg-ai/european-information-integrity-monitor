"""Research review queues, emergence and agreement; model labels stay immutable."""

from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
import random
from .core import config, digest, coherent_clusters
from .language_access import POLICY_VERSION, primary_language


def qa_sample(videos, seed, per_group=3):
    groups = {
        "high_sfi": lambda x: x["sfi"] >= 3,
        "low_sfi": lambda x: x["sfi"] < 1,
        "borderline_sfi": lambda x: 1.5 <= x["sfi"] <= 2.5,
        "high_confidence": lambda x: x["confidence"] >= 0.85,
        "low_confidence": lambda x: x["confidence"] < 0.6,
        "other": lambda x: "other" in x["narratives"],
        "high_aai": lambda x: x.get("aai") is not None and x["aai"] >= 0.7,
        "normal_aai": lambda x: x.get("aai") is not None and x["aai"] < 0.7,
        "injection": lambda x: (x.get("injection") or 0) > 0,
        "ordinary": lambda x: True,
    }
    chosen = defaultdict(list)
    for label, pred in groups.items():
        pool = sorted([x for x in videos if pred(x)], key=lambda x: x["id"])
        rng = random.Random(digest([seed, label]))
        for x in rng.sample(pool, min(per_group, len(pool))):
            chosen[x["id"]].append(label)
    # Add explicit country × tier × language coverage, still outcome-independent within cell.
    strata = defaultdict(list)
    for x in videos:
        strata[(x.get("sampling_country"), x["tier"], x.get("language", "und"))].append(
            x
        )
    for key, pool in sorted(strata.items(), key=lambda x: str(x[0])):
        x = min(pool, key=lambda x: digest([seed, key, x["id"]]))
        chosen[x["id"]].append("coverage:" + ":".join(str(k) for k in key))
    return [
        {
            "item_id": x["id"],
            "item_type": "video",
            "qa_strata": chosen[x["id"]],
            "model_label": x,
            "human_label": None,
            "adjudicated_label": None,
            "review_status": "pending",
        }
        for x in videos
        if x["id"] in chosen
    ]


def emerging(items, vectors, cfg=None):
    cfg = cfg or config("narratives")
    groups = coherent_clusters(vectors, cfg["emerging_similarity_threshold"], 1)
    out = []
    for g in groups:
        weeks = sorted(set(items[i]["week_start"] for i in g))
        dates = [datetime.fromisoformat(w) for w in weeks]
        streak = best = 1
        for a, b in zip(dates, dates[1:]):
            streak = streak + 1 if (b.date() - a.date()).days == 7 else 1
            best = max(best, streak)
        flag = (
            best >= cfg["emerging_min_weeks"]
            or len(g) >= cfg["emerging_volume_threshold"]
        )
        out.append(
            {
                "labels": sorted(set(items[i]["label"] for i in g)),
                "item_ids": [items[i]["id"] for i in g],
                "recurrence": len(g),
                "weeks": weeks,
                "consecutive_weeks": best,
                "candidate_emerging_narrative": flag,
                "review_status": "pending" if flag else "observed",
                "promoted": False,
            }
        )
    return out


def agreement(reviews):
    reviews = [
        r
        for r in reviews
        if r.get("human_label") is not None and r.get("item_type") == "video"
    ]
    if not reviews:
        return {
            "n": 0,
            "dimension_agreement": None,
            "strong_agreement": None,
            "narrative_agreement": None,
            "target_agreement": None,
        }

    def overlap(a, b):
        a, b = set(a), set(b)
        return len(a & b) / len(a | b) if a | b else 1

    dims = {
        k: sum(r["model_label"][k] == r["human_label"][k] for r in reviews)
        / len(reviews)
        for k in ["othering", "aversion", "moralization"]
    }
    strong = lambda x: all(x[k] >= 2 for k in dims)
    target = lambda x: [
        t["target_name"] if isinstance(t, dict) else t for t in x.get("targets", [])
    ]
    return {
        "n": len(reviews),
        "dimension_agreement": dims,
        "strong_agreement": sum(
            strong(r["model_label"]) == strong(r["human_label"]) for r in reviews
        )
        / len(reviews),
        "narrative_agreement": sum(
            overlap(r["model_label"]["narratives"], r["human_label"]["narratives"])
            for r in reviews
        )
        / len(reviews),
        "target_agreement": sum(
            overlap(target(r["model_label"]), target(r["human_label"])) for r in reviews
        )
        / len(reviews),
        "method": "exact dimension agreement; exact strong-frame agreement; Jaccard narrative/target agreement. Not chance-corrected reliability.",
    }


def latest_reviews(reviews):
    """A later human correction takes precedence regardless of database row order."""

    def order(r):
        try:
            at = datetime.fromisoformat(r.get("reviewed_at", "").replace("Z", "+00:00"))
            at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
            return (at.timestamp(), digest(r))
        except (ValueError, TypeError, AttributeError):
            return (float("-inf"), digest(r))

    completed = {}
    for r in sorted(reviews, key=order):
        if r.get("review_status") == "complete" and r.get("human_label") is not None:
            completed[(r["item_type"], r["item_id"], r.get("classifier_version"))] = r
    return list(completed.values())


def validation_gate(reviews, version):
    # One completed human/adjudicated review per unique item, same measurement version.
    completed = {
        r["item_type"] + ":" + r["item_id"]: r
        for r in latest_reviews(reviews)
        if r.get("review_status") == "complete"
        and r.get("human_label") is not None
        and r.get("classifier_version") == version
        and r.get("language_policy_version") == POLICY_VERSION
        and not r.get("is_fixture", False)
    }
    videos = [r for r in completed.values() if r["item_type"] == "video"]
    clusters = [r for r in completed.values() if r["item_type"] == "comment_cluster"]
    cfg = config("retention")
    # Launch additionally requires coverage recorded in the validation report.
    countries = {c for r in videos for c in r["model_label"].get("countries", [])}
    languages = {primary_language(r.get("original_audio_language")) for r in videos} - {
        "und"
    }
    tiers = {r["model_label"].get("tier") for r in videos}
    coverage = (
        len(countries) >= 3
        and len(languages) >= 2
        and {"low", "medium", "high"} <= tiers
    )
    return {
        "passed": len(videos) >= cfg["human_validation_min_videos"]
        and len(clusters) >= cfg["human_validation_min_comment_clusters"]
        and coverage,
        "videos_reviewed": len(videos),
        "clusters_reviewed": len(clusters),
        "coverage_satisfied": coverage,
        "agreement": agreement(videos),
    }
