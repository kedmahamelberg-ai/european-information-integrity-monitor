"""Compute the configured deterministic review selection from public IDs only."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from eiim.review_sampling import linked_comment_plan, sample_plan


def selection(population, batch):
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
    comments_by_video = {vid: video_comments.get(vid, []) for vid in videos}
    video_plan = sample_plan(batch, videos, comments_by_video=comments_by_video)
    comments_plan = linked_comment_plan(batch, video_plan, comments_by_video)
    return {
        "batch": batch,
        "video_population": video_plan["population"],
        "comment_population": comments_plan["population"],
        "selected_video_ids": video_plan["selected_video_ids"],
        "selected_comment_ids": comments_plan["selected_comment_ids"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = selection(json.loads(args.population.read_text()), args.batch)
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
