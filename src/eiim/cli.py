import argparse, json, os, sys
from pathlib import Path
from datetime import datetime, timezone
from .core import config, ROOT, now, digest, sfi
from .storage import Store, record
from .research import validation_gate, agreement


def preflight():
    required = ["YOUTUBE_API_KEY", "OPENAI_API_KEY", "SUPABASE_URL"]
    missing = [k for k in required if not os.environ.get(k)]
    if not (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    ):
        missing.append("SUPABASE_SECRET_KEY")
    return {
        "ready": not missing
        and os.environ.get("EIIM_ENABLE_LIVE", "false").lower() == "true",
        "missing_secret_names": missing,
        "live_enabled": os.environ.get("EIIM_ENABLE_LIVE", "false").lower() == "true",
    }


def export_public(store, path):
    batches = {
        b["id"]: b for b in store.read("weekly_batches") if b["status"] == "published"
    }
    superseded = {b["payload"].get("supersedes_batch") for b in batches.values()}
    batches = {k: b for k, b in batches.items() if k not in superseded}
    reviews = [
        r["payload"] for r in store.read("human_validation") if not r.get("purged_at")
    ]
    gate = validation_gate(reviews, config("models")["classifier_version"])
    snapshots = [
        r["payload"]
        for r in store.read("dashboard_snapshots")
        if r["batch_id"] in batches and not r.get("purged_at")
    ]
    if not gate["passed"]:
        snapshots = []
    out = {
        "mode": "live" if snapshots else "empty",
        "status": "published" if snapshots else "awaiting_validation",
        "batches": [],
        "videos": [],
        "candidates": [],
        "emerging_narratives": [],
        "validation": gate,
        "message": (
            "Published research observations; automated indicators, not attribution."
            if snapshots
            else "No validated live observations have been published. Demonstration data are synthetic."
        ),
    }
    for s in sorted(snapshots, key=lambda s: s["batch"]["window_start"]):
        b = s["batch"]
        out["batches"].append(
            {**b, "label": b["window_start"][:10] + " – " + b["window_end"][:10]}
        )
        out["videos"] += s["videos"]
        out["candidates"] += s["candidates"]
        out["emerging_narratives"] += s.get("emerging_narratives", [])
    # This output is a deployment artifact, never a commit of live raw data.
    approved = {
        r["item_id"]: r.get("approved_excerpts", [])
        for r in reviews
        if r.get("review_status") == "complete"
    }
    for video in out["videos"]:
        video["excerpts"] = approved.get(video["id"], [])[:2]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return {"published_batches": len(snapshots), "video_cases": len(out["videos"])}


def import_reviews(store, path):
    items = json.loads(path.read_text())
    known = {r["id"]: r for r in store.read("human_validation")}
    count = 0
    for item in items:
        original = known.get(item.get("queue_record_id"))
        if not original:
            raise ValueError("Unknown review queue record")
        q = original["payload"]
        human = item.get("human_label")
        if not isinstance(human, dict):
            raise ValueError("Human label is required")
        if not item.get("reviewer") or not item.get("reviewed_at"):
            raise ValueError("Reviewer and review timestamp required")
        if q["item_type"] == "video":
            sfi(*(human[k] for k in ["othering", "aversion", "moralization"]))
            if not isinstance(human.get("narratives"), list) or not isinstance(
                human.get("targets"), list
            ):
                raise ValueError("Narrative and target labels required")
        elif q["item_type"] == "comment_cluster":
            if any(
                type(human.get(k)) is not bool
                for k in ["coherent", "off_topic", "different_narrative"]
            ):
                raise ValueError("Cluster labels must contain three boolean decisions")
        elif q["item_type"] == "exclusion":
            if type(human.get("news_relevance")) is not bool:
                raise ValueError("Exclusion review requires news_relevance")
        excerpts = item.get("approved_excerpts", [])
        if (
            not isinstance(excerpts, list)
            or any(not isinstance(x, str) or len(x) > 240 for x in excerpts)
            or len(excerpts) > 2
        ):
            raise ValueError(
                "At most two researcher-approved excerpts, each at most 240 characters"
            )
        p = {
            **q,
            "approved_excerpts": excerpts,
            "human_label": human,
            "adjudicated_label": item.get("adjudicated_label"),
            "review_status": "complete",
            "reviewer": item["reviewer"],
            "reviewed_at": item["reviewed_at"],
            "source_queue_record_id": original["id"],
        }
        ident = original["id"] + ":review:" + digest(p)
        store.write(
            original["batch_id"],
            [
                record(
                    "human_validation",
                    original["batch_id"],
                    ident,
                    p,
                    original.get("video_id"),
                )
            ],
        )
        count += 1
    return {"imported_reviews": count}


def main():
    p = argparse.ArgumentParser(description="European Information Integrity Monitor")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    run = sub.add_parser("run")
    run.add_argument("--at")
    run.add_argument("--revision")
    run.add_argument("--report", default="run-report.json")
    ex = sub.add_parser("export-public")
    ex.add_argument("--output", default="build/data.json")
    review = sub.add_parser("review-export")
    review.add_argument("--batch")
    review.add_argument("--output", default="private/review-queue.json")
    im = sub.add_parser("review-import")
    im.add_argument("file")
    sub.add_parser("validation-report")
    sub.add_parser("purge")
    args = p.parse_args()
    if args.command == "preflight":
        print(json.dumps(preflight()))
        return
    if args.command == "run":
        check = preflight()
        if not check["ready"]:
            result = {"status": "not_configured", **check}
        else:
            from .pipeline import Pipeline

            store = Store()
            store.purge(config("retention")["raw_retention_days"])
            at = datetime.fromisoformat(args.at) if args.at else None
            result = Pipeline(store, at, revision=args.revision).run()
        Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return
    store = Store()
    if args.command == "purge":
        result = store.purge(config("retention")["raw_retention_days"])
    elif args.command == "export-public":
        result = export_public(store, Path(args.output))
    elif args.command == "review-export":
        records = store.read("human_validation", args.batch)
        finished = {
            x["payload"].get("source_queue_record_id")
            for x in records
            if x["payload"].get("review_status") == "complete"
        }
        candidates = {
            r["batch_id"] + ":" + r["video_id"]: r["payload"]
            for r in store.read("candidate_videos")
            if not r.get("purged_at")
        }
        comments = {
            r["id"]: r["payload"]
            for r in store.read("comments")
            if not r.get("purged_at")
        }
        out = []
        for r in records:
            if (
                r.get("purged_at")
                or r["payload"].get("review_status") != "pending"
                or r["id"] in finished
            ):
                continue
            q = r["payload"]
            item = {"queue_record_id": r["id"], **q, "reviewer": "", "reviewed_at": ""}
            key = q["item_id"]
            vid = (
                r.get("video_id")
                or q["model_label"].get("video_id")
                or key.split(":")[-1]
            )
            item["source_observation"] = candidates.get(r["batch_id"] + ":" + vid)
            item["source_comments"] = [
                comments.get(r["batch_id"] + ":" + cid)
                for cid in q["model_label"].get("comment_ids", [])
            ]
            out.append(item)
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        result = {"exported": len(out), "private_file": str(path)}
    elif args.command == "review-import":
        result = import_reviews(store, Path(args.file))
    else:
        result = validation_gate(
            [
                r["payload"]
                for r in store.read("human_validation")
                if not r.get("purged_at")
            ],
            config("models")["classifier_version"],
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
