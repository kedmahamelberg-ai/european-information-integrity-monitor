import argparse, json, os, sys
from pathlib import Path
from datetime import datetime, timezone
from .core import config, ROOT, now, digest, sfi
from .storage import Store, record
from .research import validation_gate, agreement, latest_reviews


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
        "collection": store.progress(),
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
        for r in latest_reviews(reviews)
        if r.get("review_status") == "complete"
    }
    for video in out["videos"]:
        video["excerpts"] = approved.get(video["id"], [])[:2]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return {"published_batches": len(snapshots), "video_cases": len(out["videos"])}


def import_reviews(store, path):
    from .language_access import access_records, video_access, POLICY_VERSION

    items = json.loads(path.read_text())
    known = {r["id"]: r for r in store.read("human_validation")}
    candidates = {
        (r["batch_id"], r["video_id"]): r["payload"]
        for r in store.read("candidate_videos")
        if not r.get("purged_at")
    }
    access = access_records(store.read("pipeline_runs"))
    from .review_sampling import plans_for_store, assignment

    review_plans = plans_for_store(store)
    count = 0
    prepared = []
    if not isinstance(items, list):
        raise ValueError("Review file must contain an array")
    for item in items:
        original = known.get(item.get("queue_record_id"))
        if not original or original.get("purged_at"):
            raise ValueError("Unknown review queue record")
        q = original["payload"]
        vid = (
            original.get("video_id")
            or q["model_label"].get("video_id")
            or q["item_id"].split(":")[-1]
        )
        eligibility = video_access(
            candidates.get((original["batch_id"], vid), {"video_id": vid}),
            original["batch_id"],
            access,
        )
        if not eligibility["eligible"]:
            raise ValueError(
                "Review source has no verified English access under the current pool policy"
            )
        if item.get("score_max", q["model_label"].get("score_max", 4)) != q[
            "model_label"
        ].get("score_max", 4):
            raise ValueError(
                "Review score scale does not match the immutable model queue"
            )
        human = item.get("human_label")
        if not isinstance(human, dict):
            raise ValueError("Human label is required")
        if not item.get("reviewer") or not item.get("reviewed_at"):
            raise ValueError("Reviewer and review timestamp required")
        if q["item_type"] == "video":
            scores = [human[k] for k in ["othering", "aversion", "moralization"]]
            if any(v is None for v in scores):
                if not all(v is None for v in scores) or q["model_label"].get(
                    "assessment_status"
                ) not in {"insufficient_evidence", "out_of_scope"}:
                    raise ValueError(
                        "Null scores require a complete abstention on an unscored model item"
                    )
            else:
                sfi(*scores, score_max=q["model_label"].get("score_max", 4))
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
        if "review_decisions" in item:
            from .review import validate_assisted_review

            validate_assisted_review(item, q)
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
            "language_policy_version": POLICY_VERSION,
            "original_audio_language": eligibility["original_language"],
            "english_access_status": eligibility["status"],
            "approved_excerpts": excerpts,
            "human_label": (
                dict(human, score_max=q["model_label"].get("score_max", 4))
                if q["item_type"] == "video"
                else human
            ),
            "score_max": q["model_label"].get("score_max", 4),
            "adjudicated_label": item.get("adjudicated_label"),
            "review_status": "complete",
            "reviewer": item["reviewer"],
            "reviewed_at": item["reviewed_at"],
            "source_queue_record_id": original["id"],
            "review_method": item.get("review_method", "manual_labels"),
            "review_decisions": item.get("review_decisions"),
            "review_notes": item.get("review_notes", ""),
            "review_evidence_basis": item.get("review_evidence_basis", "unspecified"),
            "review_evidence_note": item.get("review_evidence_note", ""),
            "review_assignment": (
                assignment(review_plans[original["batch_id"]], vid)
                if q["item_type"] == "video" and original["batch_id"] in review_plans
                else {"selected": False}
            ),
        }
        ident = original["id"] + ":review:" + digest(p)
        prepared.append(
            record(
                "human_validation",
                original["batch_id"],
                ident,
                p,
                original.get("video_id"),
            )
        )
        count += 1
    for batch in sorted({r["record"]["batch_id"] for r in prepared}):
        store.write(batch, [r for r in prepared if r["record"]["batch_id"] == batch])
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
    html = sub.add_parser("review-html")
    html.add_argument("--batch")
    html.add_argument("--output", default="private/review/index.html")
    im = sub.add_parser("review-import")
    im.add_argument("file")
    sub.add_parser("validation-report")
    sub.add_parser("purge")
    refresh = sub.add_parser("refresh-comments")
    refresh.add_argument("--batch", required=True)
    recode = sub.add_parser("classify-review")
    recode.add_argument("--batch")
    recode.add_argument("--limit", type=int)
    recode.add_argument("--retrieve-captions", action="store_true")
    recode.add_argument("--evaluate-only", action="store_true")
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
    if args.command == "refresh-comments":
        from .comment_refresh import refresh_comments

        result = refresh_comments(store, args.batch)
    elif args.command == "classify-review":
        from .reclassification import reclassify

        batches = store.read("weekly_batches")
        batch = args.batch or max((r["id"] for r in batches), default=None)
        if not batch or batch not in {r["id"] for r in batches}:
            raise ValueError("An existing retained batch is required")
        if args.evaluate_only:
            from .evidence_eval import run_evaluation

            result = run_evaluation(store, batch)
            if result["passed"] != result["total"]:
                print(json.dumps(result))
                raise SystemExit(
                    "Synthetic regression checks need review; candidate run stopped"
                )
        else:
            result = reclassify(
                store, batch, limit=args.limit, retrieve_captions=args.retrieve_captions
            )
    elif args.command == "purge":
        result = store.purge(config("retention")["raw_retention_days"])
    elif args.command == "export-public":
        result = export_public(store, Path(args.output))
    elif args.command == "review-html":
        from .review import prepare_review_items, write_review_html

        result = write_review_html(
            prepare_review_items(store, args.batch), Path(args.output), store.progress()
        )
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
