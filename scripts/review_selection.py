"""Compute the configured deterministic review selection from public IDs only."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from eiim.core import config, digest
from eiim.review_sampling import linked_comment_plan, sample_plan


def selection(population, batch, excluded_video_ids=None, routine_fraction=None):
    stamp = datetime.fromisoformat(population["as_of"].replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - stamp
    if age > timedelta(hours=24) or age < -timedelta(minutes=5):
        raise ValueError("A fresh retained review population is required")
    if population.get("batch") != batch:
        raise ValueError("Review population batch mismatch")
    videos = population.get("video_ids")
    video_comments = population.get("video_comments")
    if (
        not isinstance(videos, list)
        or not isinstance(video_comments, dict)
        or any(not isinstance(x, str) or not x for x in videos)
        or any(
            not isinstance(vid, str)
            or vid not in videos
            or not isinstance(ids, list)
            or any(not isinstance(cid, str) or not cid for cid in ids)
            for vid, ids in video_comments.items()
        )
    ):
        raise ValueError("Invalid review population")
    excluded = sorted(set(excluded_video_ids or []))
    if any(not isinstance(vid, str) or vid not in videos for vid in excluded):
        raise ValueError("Excluded review IDs must belong to the review population")
    if routine_fraction is not None and not 0 < routine_fraction <= 1:
        raise ValueError("Review fraction must be between zero and one")
    eligible_videos = [vid for vid in videos if vid not in excluded]
    comments_by_video = {
        vid: video_comments.get(vid, []) for vid in eligible_videos
    }
    policy = None
    if excluded or routine_fraction is not None:
        policy = dict(config("review_sampling"))
        policy["calibration_batch"] = ""
        policy["routine_fraction"] = (
            routine_fraction
            if routine_fraction is not None
            else policy["routine_fraction"]
        )
        policy["version"] = policy["version"] + "-supplemental"
        policy["seed"] = policy["seed"] + ":supplemental:" + digest(excluded)
    video_plan = sample_plan(
        batch,
        eligible_videos,
        policy=policy,
        comments_by_video=comments_by_video,
    )
    if excluded:
        video_plan["overall_population"] = len(videos)
        video_plan["excluded_video_ids"] = excluded
        video_plan["selection_method"] += (
            f"; disjoint from {len(excluded)} previously assigned videos"
        )
    comments_plan = linked_comment_plan(
        batch, video_plan, comments_by_video, policy=policy
    )
    return {
        "batch": batch,
        "video_population": video_plan["population"],
        "comment_population": comments_plan["population"],
        "selected_video_ids": video_plan["selected_video_ids"],
        "selected_comment_ids": comments_plan["selected_comment_ids"],
        "plan": video_plan,
        "comment_plan": comments_plan,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-selection", type=Path)
    parser.add_argument("--fraction", type=float)
    args = parser.parse_args()
    excluded = []
    if args.exclude_selection:
        previous = json.loads(args.exclude_selection.read_text())
        if previous.get("batch") != args.batch:
            raise ValueError("Excluded review selection batch mismatch")
        excluded = previous.get("selected_video_ids", [])
    data = selection(
        json.loads(args.population.read_text()),
        args.batch,
        excluded_video_ids=excluded,
        routine_fraction=args.fraction,
    )
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data))
    os.chmod(args.output, 0o600)
    print(json.dumps({
        "video_population": data["video_population"],
        "comment_population": data["comment_population"],
        "selected_videos": len(data["selected_video_ids"]),
        "selected_comments": len(data["selected_comment_ids"]),
        "path": str(args.output),
    }))


if __name__ == "__main__":
    main()
