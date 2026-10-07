"""War/security framing of retained evidence; no source retrieval in reclassification."""

import argparse
import json
import re
import copy
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .core import ROOT, config, digest, now
from .language_access import (
    access_records,
    video_access,
    translated_comment,
    TRANSLATION_VERSION,
)
from .model_policy import selected_policy
from .reclassification import evidence_input
from .review_sampling import plans_for_store, assignment
from .services import Classifier, Ledger, BudgetExhausted, ClassificationUnavailable
from .storage import Store, record

VERSION = "hybrid-framing-1.4"
COMMENT_VERSION = "hybrid-comments-1.3"


def obj(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def enum(name):
    return {"type": "string", "enum": config("hybrid")[name]}


def schema():
    string = {"type": "string"}
    evidence = obj({"quote": string, "source_id": string})
    role = obj(
        {
            "entity": string,
            "entity_code": {
                "type": "string",
                "enum": [c["iso2"] for c in config("countries")["countries"]]
                + ["EU", "OTHER"],
            },
            "role": enum("roles"),
            "evidence": evidence,
            "rationale": string,
        }
    )
    comment = obj(
        {
            "comment_id": string,
            "alignment": enum("alignment"),
            "stance_target": string,
            "response_focus": enum("response_focus"),
            "sentiment": enum("sentiment"),
            "sentiment_target": string,
            "rationale": string,
        }
    )
    return obj(
        {
            "relevance": enum("relevance"),
            "topics": {"type": "array", "items": enum("topics")},
            "evidence_status": enum("evidence_status"),
            "evidence": evidence,
            "rationale": string,
            "roles": {"type": "array", "items": role},
            "content_reference": obj(
                {
                    "summary": string,
                    "speaker": string,
                    "target": string,
                    "speaker_sentiment": enum("sentiment"),
                    "evidence": evidence,
                }
            ),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "comments": {"type": "array", "items": comment},
            "execution": {
                "type": "array",
                "items": obj(
                    {
                        "category": enum("execution"),
                        "status": enum("execution_status"),
                        "evidence": evidence,
                        "rationale": string,
                    }
                ),
            },
        }
    )


def validate_shape(value, shape):
    """Validate the small strict-schema subset locally as well as at the API."""
    typ = shape["type"]
    if typ == "object":
        if not isinstance(value, dict) or set(value) != set(shape["properties"]):
            raise ValueError("Incorrect result fields")
        for key, child in shape["properties"].items():
            validate_shape(value[key], child)
    elif typ == "array":
        if not isinstance(value, list):
            raise ValueError("Expected array")
        for child in value:
            validate_shape(child, shape["items"])
    elif typ == "string":
        if not isinstance(value, str) or (
            "enum" in shape and value not in shape["enum"]
        ):
            raise ValueError("Invalid label")
    elif typ == "number":
        if type(value) not in (int, float) or not shape.get(
            "minimum", 0
        ) <= value <= shape.get("maximum", 1):
            raise ValueError("Invalid confidence")


def validate_label(value, document):
    value = copy.deepcopy(value)
    validate_shape(value, schema())
    errors = []
    sections = {s["id"]: s["text"] for s in document["sections"]}

    def evidence(e, required=False, field="evidence"):
        if required and not e["quote"].strip():
            errors.append(field + ": a short exact evidence quotation is required")
        if e["quote"] and e["quote"] not in sections.get(e["source_id"], ""):
            # Caption lines often omit punctuation or split a sentence. Resolve
            # formatting-only differences to the actual source substring; never
            # accept paraphrases, reordered words, or omitted negations.
            words = re.findall(r"\w+", e["quote"].casefold())
            found = False
            for key in dict.fromkeys([e["source_id"], "transcript"]):
                source = sections.get(key, "")
                spans = list(re.finditer(r"\w+", source))
                tokens = [m.group().casefold() for m in spans]
                for i in range(len(tokens) - len(words) + 1):
                    if len(words) >= 3 and tokens[i : i + len(words)] == words:
                        e.update(
                            quote=source[
                                spans[i].start() : spans[i + len(words) - 1].end()
                            ],
                            source_id=key,
                        )
                        found = True
                        break
                if found:
                    break
            if not found:
                errors.append(
                    field
                    + ": quotation not found. Replace this field with a SHORT verbatim substring copied from a supplied transcript section and its correct source_id. Do not paraphrase or add/remove words."
                )

    evidence(value["evidence"], value["relevance"] == "related")
    if value["relevance"] != "related" and (value["topics"] or value["roles"]):
        errors.append("Only relevant videos can have study topics/roles")
    if value["relevance"] == "related" and not value["topics"]:
        errors.append("Relevant videos require at least one topic")
    if len(value["topics"]) != len(set(value["topics"])):
        errors.append("Return unique topics")
    seen = set()
    for role in value["roles"]:
        evidence(role["evidence"], True, "roles[" + str(len(seen)) + "].evidence")
        key = (role["entity"].casefold(), role["role"])
        if key in seen or not role["entity"].strip() or not role["rationale"].strip():
            errors.append(
                "Return only ONE entry for each entity + role pair, with nonempty entity and rationale. Sovereign governance is not military readiness evidence."
            )
        seen.add(key)
    reference = value["content_reference"]
    if not all(reference[k].strip() for k in ["summary", "speaker", "target"]):
        errors.append(
            "A main message, attributed speaker (or unidentified) and target (or unspecified) are required"
        )
    evidence(reference["evidence"], True, "content_reference.evidence")
    ids = [c["comment_id"] for c in value["comments"]]
    expected = [c["comment_id"] for c in document["comments"]]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        errors.append("Return each supplied comment ID exactly once")
    try:
        validate_comment_targets(value["comments"])
    except ValueError as error:
        errors.append(str(error))
    ex = value["execution"]
    if len(ex) != len(config("hybrid")["execution"]) or {
        x["category"] for x in ex
    } != set(config("hybrid")["execution"]):
        errors.append("Return each configured execution category exactly once")
    for x in ex:
        if (x["status"] == "not_applicable") == (value["relevance"] == "related"):
            errors.append(
                x["category"]
                + ": "
                + (
                    "not_applicable is forbidden for a related video. Return present only with an exact transcript quotation; otherwise not_observed_in_transcript or not_observable. Missing evidence is NOT not_applicable."
                    if value["relevance"] == "related"
                    else "For not_related/unclear videos ALL four execution statuses must be not_applicable, regardless of delivery features."
                )
            )
        if x["status"] == "present":
            evidence(x["evidence"], True, "execution." + x["category"] + ".evidence")
            if not x["evidence"]["source_id"].startswith("transcript"):
                errors.append("Execution requires transcript evidence")
    if errors:
        raise ValueError("Validation issues: " + " | ".join(errors))
    return value


def repair_evidence_options(document, parsed):
    """Retrieve short original caption excerpts for a failed model citation.

    This offers source text to a retry; it never repairs or accepts a quotation
    automatically. The complete result must still pass strict validation.
    """
    quotes = []

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("quote"), str) and value["quote"].strip():
                quotes.append(value["quote"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(parsed)
    sections = [
        s for s in document.get("sections", []) if s["id"].startswith("transcript:")
    ]
    selected = {}
    for quote in quotes[:16]:
        words = set(re.findall(r"\w+", quote.casefold()))
        if not words:
            continue
        ranked = sorted(
            sections,
            key=lambda s: len(words & set(re.findall(r"\w+", s["text"].casefold()))),
            reverse=True,
        )
        for section in ranked[:2]:
            selected[section["id"]] = {
                "source_id": section["id"],
                "text": section["text"][:600],
            }
    return list(selected.values())[:16]


def comment_schema(ids=None):
    shape = obj({"comments": schema()["properties"]["comments"]})
    if ids is not None:
        shape["properties"]["comments"]["items"]["properties"]["comment_id"] = {
            "type": "string",
            "enum": list(ids),
        }
        shape["properties"]["comments"].update(minItems=len(ids), maxItems=len(ids))
    return shape


def validate_comment_targets(comments):
    for c in comments:
        if c["response_focus"] in {"speaker", "presentation", "unrelated"} and c[
            "alignment"
        ] in {"supports", "opposes", "mixed"}:
            raise ValueError(
                "Speaker/presentation-only reactions do not establish main-message alignment; use no_position, unrelated or unclear. Use mixed focus if the main message is also addressed."
            )
        if not c["rationale"].strip():
            raise ValueError("Comment rationale required")
        if (
            c["alignment"] in {"supports", "opposes", "mixed"}
            and not c["stance_target"].strip()
        ):
            raise ValueError(
                "Comment stance requires an explicit target in the video content"
            )


def validate_comments(value, document):
    validate_shape(value, comment_schema())
    actual = [c["comment_id"] for c in value["comments"]]
    expected = [c["comment_id"] for c in document["comments"]]
    if len(set(actual)) != len(actual) or set(actual) != set(expected):
        raise ValueError(
            "Return EXACTLY these comment IDs, once each: " + json.dumps(expected)
        )
    validate_comment_targets(value["comments"])
    return value


def retained_inputs(store, batch):
    runs = [r for r in store.read("pipeline_runs", batch) if not r.get("purged_at")]
    access = access_records(runs)
    candidates = {
        r["video_id"]: r["payload"]
        for r in store.read("candidate_videos", batch)
        if not r.get("purged_at")
    }
    videos = {}
    for row in store.read("sampled_videos", batch):
        vid = row["video_id"]
        if (
            row.get("purged_at")
            or not row["payload"].get("selected_for_sample")
            or vid not in candidates
        ):
            continue
        source = {**row["payload"], **candidates[vid], "video_id": vid}
        snapshots = [
            r["payload"] for r in runs if r["payload"].get("engagement_video_id") == vid
        ]
        if snapshots:
            source["engagement_snapshot"] = max(
                snapshots, key=lambda p: p["captured_at"]
            )
        language = video_access(source, batch, access)
        if language["eligible"] and any(
            s.get("text", "").strip() for s in language.get("transcript_english", [])
        ):
            videos[vid] = (source, language)
    comments = [
        r["payload"]
        for r in store.read("comments", batch)
        if not r.get("purged_at") and r["video_id"] in videos
    ]
    translations = {
        r["payload"]["comment_translation_id"]: r["payload"]
        for r in sorted(runs, key=lambda r: r["payload"].get("translated_at", ""))
        if r["payload"].get("comment_translation_id")
    }
    return videos, comments, translations, runs


def labels(store, batch=None):
    return [
        r
        for r in store.read("pipeline_runs", batch)
        if not r.get("purged_at")
        and r["payload"].get("hybrid_version") == VERSION
        and "label" in r["payload"]
    ]


def reclassify(store, batch, classifier=None):
    batches = store.read("weekly_batches", batch)
    if not batches:
        raise ValueError("Unknown retained batch")
    stamp = batches[0].get("created_at") or batches[0]["payload"].get(
        "collection_timestamp"
    )
    if stamp and datetime.fromisoformat(stamp.replace("Z", "+00:00")) < datetime.now(
        timezone.utc
    ) - timedelta(days=30):
        raise ValueError("Retained batch has expired")
    videos, comments, translations, runs = retained_inputs(store, batch)
    classifier = classifier or Classifier(store, batch, Ledger(store, batch))
    classifier.cfg = {
        **classifier.cfg,
        "classifier_version": VERSION + "-" + selected_policy()["model"],
        "prompt_version": VERSION,
    }
    prompt = (ROOT / "prompts" / (VERSION + ".txt")).read_text()
    done = {r["id"] for r in runs}
    errors = []
    status = "complete"
    from .calibration import current_reviews, calibration_examples

    reviewed = current_reviews(store, batch)
    completed = {r["video_id"]: r for r in latest_labels(labels(store, batch))}
    for vid, (source, language) in sorted(videos.items()):
        existing = completed.get(vid)
        if existing and (existing["id"], None) in reviewed:
            continue  # Never overwrite a completed human review during retries.
        selected = sorted(
            [c for c in comments if c["video_id"] == vid], key=lambda c: c["comment_id"]
        )
        # All existing translations are reused. Missing translations use retained
        # text only; this never calls YouTube or retrieves captions/comments.
        try:
            for comment in selected:
                cid = comment["comment_id"]
                if (
                    translations.get(cid, {}).get("translation_version")
                    != TRANSLATION_VERSION
                ):
                    translated = translated_comment(comment, classifier)
                    store.write(
                        batch,
                        [
                            record(
                                "pipeline_runs",
                                batch,
                                batch
                                + ":translation-en:"
                                + TRANSLATION_VERSION
                                + ":"
                                + cid,
                                translated,
                                vid,
                            )
                        ],
                    )
                    translations[cid] = translated
            document = evidence_input(source, language)
            # Explicit reviewer observations remain attributed source evidence,
            # separate from AI suggestions and from complete human label reviews.
            feedback = sorted(
                [
                    r
                    for r in runs
                    if not r.get("purged_at")
                    and r["payload"].get("reviewer_context_video_id") == vid
                ],
                key=lambda r: r["payload"].get("recorded_at", ""),
            )
            if feedback:
                note = feedback[-1]["payload"]
                document["reviewer_context"] = {
                    "reviewer": note["reviewer"],
                    "observation": note["observation"],
                    "basis": note["basis"],
                }

            document["calibration_examples"] = calibration_examples(
                store, exclude_video_id=vid
            )
            document["entity_codes"] = {
                c["country_name"]: c["iso2"] for c in config("countries")["countries"]
            }
            document["comments"] = [
                {
                    "comment_id": c["comment_id"],
                    "text_english": translations[c["comment_id"]]["text_english"],
                }
                for c in selected
            ]
            ident = (
                batch
                + ":hybrid:"
                + VERSION
                + ":"
                + vid
                + ":"
                + digest(
                    [
                        document,
                        classifier.cfg,
                        prompt,
                        (ROOT / "prompts" / (COMMENT_VERSION + ".txt")).read_text(),
                        TRANSLATION_VERSION,
                    ]
                )[:20]
            )
            if ident in done:
                continue
            video_document = dict(document, comments=[])
            result = classifier.request(
                json.dumps(video_document, ensure_ascii=False),
                prompt,
                schema(),
                "hybrid",
            )
            label = validate_label(result["parsed"], video_document)
            all_comments = []
            comment_models = []
            for offset in range(0, len(document["comments"]), 5):
                comment_input = {
                    "calibration_examples": document["calibration_examples"][
                        "comments"
                    ],
                    "content_reference": label["content_reference"],
                    "reviewer_context": document.get("reviewer_context"),
                    "sections": document["sections"],
                    "transcript_truncated": document["transcript_truncated"],
                    "comments": document["comments"][offset : offset + 5],
                }
                comment_result = classifier.request(
                    json.dumps(comment_input, ensure_ascii=False),
                    (ROOT / "prompts" / (COMMENT_VERSION + ".txt")).read_text(),
                    comment_schema(
                        [c["comment_id"] for c in comment_input["comments"]]
                    ),
                    "hybrid_comments",
                )
                all_comments.extend(
                    validate_comments(comment_result["parsed"], comment_input)[
                        "comments"
                    ]
                )
                comment_models.append(comment_result["model_version"])
            label["comments"] = all_comments
            label = validate_label(label, document)
            payload = {
                "hybrid_version": VERSION,
                "video_id": vid,
                "label": label,
                "evidence_scope": document["scope"],
                "transcript_truncated": document["transcript_truncated"],
                "input_hash": digest(document),
                "source_language": language["original_language"],
                "model_name": result["model_name"],
                "model_version": result["model_version"],
                "classified_at": result["classification_timestamp"],
                "human_validated": False,
                "comment_models": sorted(set(comment_models)),
                "pipeline_method": "video_then_comment_batches_v1",
                "reviewer_context": document.get("reviewer_context"),
            }
            store.write(batch, [record("pipeline_runs", batch, ident, payload, vid)])
            done.add(ident)
            print(
                json.dumps({"completed_video": vid, "comments": len(selected)}),
                flush=True,
            )
        except BudgetExhausted:
            status = "pending_budget"
            break
        except (ClassificationUnavailable, ValueError) as error:
            errors.append({"video_id": vid, "error_type": type(error).__name__})
    current = latest_labels(labels(store, batch))
    coverage = caption_coverage(store, batch)
    classification_status = status if not errors else "partial"
    overall_status = classification_status
    if classification_status == "complete" and coverage["awaiting_transcripts"]:
        overall_status = "awaiting_transcripts"
    report = {
        "hybrid_report": VERSION,
        "batch": batch,
        "status": overall_status,
        "classification_status": classification_status,
        "coverage": coverage,
        "human_review_required_for_classification": False,
        "eligible_videos": len(videos),
        "classified_videos": len(current),
        "retained_comments": len(comments),
        "classified_comments": sum(
            len(r["payload"]["label"]["comments"]) for r in current
        ),
        "failures": errors,
        "new_source_collection": False,
        "at": now(),
    }
    store.write(
        batch,
        [
            record(
                "pipeline_runs",
                batch,
                batch + ":hybrid-report:" + digest(report),
                report,
            )
        ],
    )
    return report


def latest_labels(rows):
    latest = {}
    for row in sorted(rows, key=lambda r: r["payload"]["classified_at"]):
        latest[(row["batch_id"], row["video_id"])] = row
    return list(latest.values())


def collect_week(store):
    """The scheduled collector now feeds the new lens, never the retired SFI."""
    from .pipeline import Pipeline
    from .services import YouTube, LocalModel

    pipe = Pipeline(store)
    existing = store.read("weekly_batches", pipe.id)
    batch = (
        existing[0]
        if existing
        else store.batch(
            pipe.window, digest({"study": VERSION, "sampling": config("sampling")})
        )
    )
    pipe.window = batch["payload"]
    done = batch["completed_stages"]
    pipe.yt = YouTube(store, pipe.id, pipe.ledger)
    pipe.local = LocalModel(pipe.ledger)
    pipe.classifier = Classifier(store, pipe.id, pipe.ledger)
    if "discovery_complete" not in done:
        pipe.discovery()
    if "sampling_complete" not in done:
        pipe.sampling()
    pipe.prepare_english_access()
    retrieve_retained_captions(store, pipe.id)
    # Only transcript-eligible sources enter the new comment pool.
    eligible = set(retained_inputs(store, pipe.id)[0])
    pipe.active_samples = lambda: [
        s
        for s in pipe.values("sampled_videos")
        if s.get("selected_for_sample") and s["video_id"] in eligible
    ]
    if "comments_complete" not in done:
        pipe.comments()
    return reclassify(store, pipe.id, pipe.classifier)


def caption_coverage(store, batch):
    """Report the entire sample separately from the transcript-eligible subset."""
    from .language_access import caption_state

    sampled = {r["video_id"] for r in store.read("sampled_videos", batch)
               if not r.get("purged_at") and r["payload"].get("selected_for_sample")}
    sources = {r["video_id"]: r["payload"] for r in store.read("candidate_videos", batch)
               if not r.get("purged_at")}
    accesses = access_records(store.read("pipeline_runs", batch))
    counts = Counter(caption_state(video_access(dict(sources.get(vid, {}), video_id=vid), batch, accesses))
                     for vid in sampled)
    return {"sampled_videos": len(sampled), "saved_transcripts": counts["saved"],
            "awaiting_transcripts": len(sampled) - counts["saved"],
            "retrieval_blocked": counts["blocked"], "english_unavailable": counts["unavailable"],
            "unverified": counts["unverified"]}


def retrieve_retained_captions(store, batch, audio=None):
    """Attempt public English captions for frozen sources only; never discover videos."""
    from .language_access import EnglishCaptionAccess

    access = access_records(store.read("pipeline_runs", batch))
    sampled = {
        r["video_id"]
        for r in store.read("sampled_videos", batch)
        if not r.get("purged_at") and r["payload"].get("selected_for_sample")
    }
    from .caption_provider import SupadataCaptions
    from .audio_transcripts import AudioTranscripts

    reader = EnglishCaptionAccess()
    fallback = SupadataCaptions.from_environment(store, batch)
    audio = audio or AudioTranscripts.from_environment()
    retrieved = 0
    attempted = 0
    # Untouched sources first; failed sources cannot monopolise every daily run.
    candidates = sorted(store.read("candidate_videos", batch), key=lambda r: (
        access.get((batch, r["video_id"]), {}).get("audio_attempted_at", ""), r["id"]))
    for row in candidates:
        if row.get("purged_at") or row["video_id"] not in sampled:
            continue
        source = dict(row["payload"], video_id=row["video_id"])
        old = video_access(source, batch, access)
        if any(s.get("text", "").strip() for s in old.get("transcript_english", [])):
            continue
        result = reader.check(source, retrieve_english_audio=True)
        attempted += 1
        if not result.get("transcript_english") and fallback:
            recovered = fallback.check(source)
            if recovered is not None:
                recovered["direct_failure_reason"] = result.get("failure_reason")
                result = recovered
        if not result.get("transcript_english") and audio:
            previous_attempt = old.get("audio_attempted_at")
            due = not previous_attempt or datetime.fromisoformat(previous_attempt) < datetime.now(timezone.utc) - timedelta(hours=24)
            if due:
                recovered = audio.check(source)
                if recovered is not None:
                    recovered["direct_failure_reason"] = result.get("failure_reason")
                    result = recovered
                    print(json.dumps({"audio_recovery": audio.report()}), flush=True)
            elif previous_attempt:
                result["audio_attempted_at"] = previous_attempt
        # Keep previously known original-language metadata if a track lookup fails.
        if (
            result.get("original_language") == "und"
            and old.get("original_language") != "und"
        ):
            result.update(
                original_language=old["original_language"],
                language_basis=old.get("language_basis", "previous_caption_check"),
            )
        store.write(
            batch,
            [
                record(
                    "pipeline_runs",
                    batch,
                    batch + ":hybrid-caption:" + digest([row["video_id"], result]),
                    result,
                    row["video_id"],
                )
            ],
        )
        retrieved += bool(result.get("transcript_english"))
        if reader.blocked and (not fallback or fallback.stopped) and (not audio or audio.stopped):
            break
    report = {"new_saved_transcripts": retrieved, "attempted_videos": attempted,
            "direct_reader_blocked": reader.blocked,
            "fallback": fallback.report() if fallback else {"configured": False},
            "audio": audio.report() if audio else {"configured": False},
            "coverage": caption_coverage(store, batch)}
    payload = {"caption_recovery_report": report, "checked_at": now()}
    store.write(batch, [record("pipeline_runs", batch, batch + ":caption-health:" + digest(payload), payload)])
    return report


def refresh_engagement(store, batch, youtube=None):
    """Refresh counters only for existing transcript-eligible videos."""
    from .services import YouTube

    ids = sorted(retained_inputs(store, batch)[0])
    youtube = youtube or YouTube(store, batch, Ledger(store, batch))
    captured = now()
    refreshed = 0
    for offset in range(0, len(ids), 50):
        response = youtube.get(
            "videos",
            part="statistics",
            id=",".join(ids[offset : offset + 50]),
            cache_scope="engagement:" + captured,
        )
        for item in response.get("items", []):
            vid = item["id"]
            if vid not in ids or not isinstance(item.get("statistics"), dict):
                continue
            payload = {
                "engagement_video_id": vid,
                "captured_at": captured,
                "statistics": item["statistics"],
            }
            store.write(
                batch,
                [
                    record(
                        "pipeline_runs",
                        batch,
                        batch + ":engagement:" + digest(payload),
                        payload,
                        vid,
                    )
                ],
            )
            refreshed += 1
    return {"refreshed_engagement_videos": refreshed, "new_source_collection": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--retrieve-captions", action="store_true")
    parser.add_argument("--refresh-engagement", action="store_true")
    parser.add_argument("--all-retained", action="store_true", help="Resume every unpurged retained batch, newest first")
    args = parser.parse_args()
    store = Store()
    if args.collect:
        report = collect_week(store)
    else:
        from .audio_transcripts import AudioTranscripts
        audio = AudioTranscripts.from_environment()
        batches = sorted((r["id"] for r in store.read("weekly_batches")), reverse=True)
        batches = [args.batch] if args.batch else (batches if args.all_retained else batches[:1])
        reports = []
        for batch in batches:
            if not any(not r.get("purged_at") and r["payload"].get("selected_for_sample") for r in store.read("sampled_videos", batch)):
                continue
            if args.retrieve_captions:
                print(json.dumps(retrieve_retained_captions(store, batch, audio)), flush=True)
            if args.refresh_engagement:
                print(json.dumps(refresh_engagement(store, batch)), flush=True)
            report = reclassify(store, batch)
            reports.append(report)
            print(json.dumps(report, indent=2), flush=True)
        if any(r["status"] != "complete" for r in reports):
            raise SystemExit(1)
        return
    print(json.dumps(report, indent=2))
    if report["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
