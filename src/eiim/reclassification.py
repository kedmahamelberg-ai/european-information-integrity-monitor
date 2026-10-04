"""Evidence-grounded candidate labels, separate from frozen analytical baselines."""

import copy
import json
from collections import Counter

from .core import ROOT, config, digest, now, validate_classification
from .language_access import access_records, video_access
from .storage import record

VERSION = "classifier-1.1"
PROMPT = "sfi-1.1.1"
DIMENSIONS = ("othering", "aversion", "moralization")
TRANSCRIPT_CHAR_LIMIT = 48000


def evidence_input(video, access):
    sections = [
        {"id": "title", "text": video.get("title") or ""},
        {"id": "description", "text": video.get("description") or ""},
    ]
    used = 0
    included = 0
    segments = access.get("transcript_english", [])
    for i, segment in enumerate(segments):
        text = segment.get("text", "").strip()
        if not text:
            continue
        if used + len(text) > TRANSCRIPT_CHAR_LIMIT:
            break
        sections.append(
            {"id": f"transcript:{i}", "text": text, "start_seconds": segment["start"]}
        )
        used += len(text)
        included += 1
    # Contiguous text permits evidence spanning adjacent caption lines. Segment IDs
    # and timestamps remain available to the reviewer for locating the passage.
    if included:
        sections.append(
            {"id": "transcript", "text": " ".join(s["text"] for s in sections[2:])}
        )
    truncated = included < sum(bool(s.get("text", "").strip()) for s in segments)
    return {
        "scope": "metadata_and_english_transcript" if included else "metadata_only",
        "original_audio_language": access.get("original_language", "und"),
        "transcript_truncated": truncated,
        "transcript_segments_included": included,
        "transcript_segments_available": len(segments),
        "sections": sections,
    }


def evidence_schema():
    from .services import schema

    shape = schema()
    props = shape["properties"]
    for k in DIMENSIONS:
        props[k] = {"type": ["integer", "null"], "minimum": 0, "maximum": 4}
    props.update(
        assessment_status={
            "type": "string",
            "enum": ["scored", "insufficient_evidence", "out_of_scope"],
        },
        public_affairs_relevance={
            "type": "string",
            "enum": ["in_scope", "out_of_scope", "unclear"],
        },
        publisher_stance={
            "type": "string",
            "enum": ["asserted", "reported_only", "rejected", "mixed", "unclear"],
        },
        dimension_evidence={
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": list(DIMENSIONS)},
                    **{
                        k: {"type": "string"}
                        for k in [
                            "quote",
                            "source_id",
                            "target",
                            "speaker",
                            "explanation",
                        ]
                    },
                    "attribution": {
                        "type": "string",
                        "enum": [
                            "author_assertion",
                            "speaker_assertion",
                            "reported_only",
                            "rejected",
                            "unclear",
                            "none",
                        ],
                    },
                },
                "required": [
                    "dimension",
                    "quote",
                    "source_id",
                    "target",
                    "speaker",
                    "explanation",
                    "attribution",
                ],
                "additionalProperties": False,
            },
        },
    )
    shape["required"] = list(props)
    return shape


def validate_evidence_label(raw, document):
    """Reject unsupported scores/quotes; abstentions never become numerical zeros."""
    x = copy.deepcopy(raw)
    status = x.get("assessment_status")
    if status not in {"scored", "insufficient_evidence", "out_of_scope"}:
        raise ValueError("Invalid assessment status")
    if x.get("public_affairs_relevance") not in {"in_scope", "out_of_scope", "unclear"}:
        raise ValueError("Invalid relevance status")
    if x.get("publisher_stance") not in {
        "asserted",
        "reported_only",
        "rejected",
        "mixed",
        "unclear",
    }:
        raise ValueError("Invalid publisher stance")
    if (status == "out_of_scope") != (x["public_affairs_relevance"] == "out_of_scope"):
        raise ValueError("Out-of-scope status must agree with relevance")
    scores = [x.get(k) for k in DIMENSIONS]
    if status != "scored" and any(v is not None for v in scores):
        raise ValueError("Insufficient/out-of-scope evidence requires null scores")
    check = copy.deepcopy(x)
    if status != "scored":
        check.update({k: 0 for k in DIMENSIONS})
    # Legacy validation requires negative affect even for social-distance-only
    # othering. Relax only this gate, then validate actual dimension targets below.
    if check["othering"] and not check["aversion"] and not check["moralization"]:
        for target in check.get("targets", []):
            if target.get("direction") == "unclear":
                target["direction"] = "negative"
    validated = validate_classification(check)
    evidence = x.get("dimension_evidence", [])
    if len(evidence) != 3 or {e.get("dimension") for e in evidence} != set(DIMENSIONS):
        raise ValueError("Supply exactly one evidence entry per dimension")
    sections = {s["id"]: s["text"] for s in document["sections"]}
    targets = {t["target_name"]: t for t in x["targets"]}
    for e in evidence:
        if not all(
            isinstance(e.get(k), str)
            for k in [
                "quote",
                "source_id",
                "target",
                "speaker",
                "explanation",
                "attribution",
            ]
        ):
            raise ValueError("Invalid evidence entry")
        if not e["explanation"].strip():
            raise ValueError("Every dimension needs an explanation")
        quote = e["quote"]
        if quote and (
            len(quote) > 400 or quote not in sections.get(e["source_id"], "")
        ):
            raise ValueError(
                "Evidence quote must be verbatim in its source section and <=400 characters"
            )
        score = x[e["dimension"]]
        if score is not None and score > 0:
            target = targets.get(e["target"])
            if (
                not quote
                or not target
                or not e["speaker"].strip()
                or e["attribution"] not in {"author_assertion", "speaker_assertion"}
            ):
                raise ValueError(
                    "Nonzero score requires quoted, attributed evidence and its named target"
                )
            if e["dimension"] != "othering" and target["direction"] not in {
                "negative",
                "mixed",
            }:
                raise ValueError(
                    "Aversion/moralization require negative or mixed treatment of the evidence target"
                )
            if target["direction"] == "positive":
                raise ValueError("Positive-only target is not a sectarian cue")
    return dict(
        x,
        sfi=validated["sfi"] if status == "scored" else None,
        strong_sectarian_frame=(
            validated["strong_sectarian_frame"] if status == "scored" else None
        ),
    )


def configure_candidate(classifier):
    classifier.cfg = dict(
        classifier.cfg,
        classifier_version=VERSION,
        prompt_version=PROMPT,
        max_output_tokens=3000,
    )
    return classifier


def classify_document(classifier, document):
    return classifier.request(
        json.dumps(document, ensure_ascii=False),
        (ROOT / f"prompts/{PROMPT}.txt").read_text(),
        evidence_schema(),
        "sfi_review",
    )


def reclassify(store, batch, classifier=None, limit=None, retrieve_captions=False):
    from .services import Classifier, Ledger, BudgetExhausted, ClassificationUnavailable

    classifier = configure_candidate(
        classifier or Classifier(store, batch, Ledger(store, batch))
    )
    from .language_access import EnglishCaptionAccess

    captions = EnglishCaptionAccess() if retrieve_captions else None
    sidecars = store.read("pipeline_runs", batch)
    access = access_records(sidecars)
    candidates = {
        r["video_id"]: r["payload"]
        for r in store.read("candidate_videos", batch)
        if not r.get("purged_at")
    }
    originals = {
        r["video_id"]: r
        for r in store.read("video_classifications", batch)
        if not r.get("purged_at")
    }
    sampled = {
        r["video_id"]: r["payload"]
        for r in store.read("sampled_videos", batch)
        if not r.get("purged_at") and r["payload"].get("selected_for_sample")
    }
    cached = {r["id"]: r["payload"] for r in sidecars if not r.get("purged_at")}
    pending, outcomes, processed = [], [], 0
    # Reviewed sources first, followed by a stable, outcome-independent order.
    reviewed = {
        r["video_id"]
        for r in store.read("human_validation", batch)
        if not r.get("purged_at") and r["payload"].get("review_status") == "complete"
    }
    for vid in sorted(sampled, key=lambda v: (v not in reviewed, digest([batch, v]))):
        video = candidates.get(vid)
        if not video:
            continue
        eligibility = video_access(video, batch, access)
        if not eligibility["eligible"]:
            continue
        if (
            captions
            and not eligibility.get("transcript_english")
            and not eligibility.get("transcript_checked")
        ):
            # English audio stays eligible even if captions cannot be retrieved.
            fetched = captions.check(
                dict(video, original_audio_language=eligibility["original_language"]),
                retrieve_english_audio=True,
            )
            if fetched["eligible"]:
                eligibility = fetched
                store.write(
                    batch,
                    [
                        record(
                            "pipeline_runs",
                            batch,
                            f"{batch}:english-access:{vid}:" + digest(fetched),
                            fetched,
                            vid,
                        )
                    ],
                )
        document = evidence_input(video, eligibility)
        input_hash = digest(
            [
                document,
                (ROOT / f"prompts/{PROMPT}.txt").read_text(),
                evidence_schema(),
                classifier.cfg,
            ]
        )
        ident = f"{batch}:reclassification:{VERSION}:{vid}:{input_hash}"
        label = cached.get(ident)
        if label is None:
            if limit is not None and processed >= limit:
                pending.append(vid)
                continue
            try:
                result = classify_document(classifier, document)
            except BudgetExhausted:
                pending.append(vid)
                continue
            except ClassificationUnavailable:
                pending.append(vid)
                continue
            processed += 1
            meta = {
                k: result[k]
                for k in [
                    "model_provider",
                    "model_name",
                    "model_version",
                    "prompt_version",
                    "taxonomy_version",
                    "classifier_version",
                    "classification_timestamp",
                ]
            }
            label = {
                **result["parsed"],
                **meta,
                "reclassification_video_id": vid,
                "video_id": vid,
                "evidence_scope": document["scope"],
                "input_hash": input_hash,
                "input_sections": document["sections"],
                "transcript_truncated": document["transcript_truncated"],
                "transcript_segments_included": document[
                    "transcript_segments_included"
                ],
                "transcript_segments_available": document[
                    "transcript_segments_available"
                ],
                "original_audio_language": eligibility["original_language"],
                "validation_status": "candidate_awaiting_human_validation",
                "baseline_record_id": originals.get(vid, {}).get("id"),
                "baseline_scores": {
                    k: originals.get(vid, {}).get("payload", {}).get(k)
                    for k in DIMENSIONS
                },
                "raw_response_ref": batch
                + ":model:"
                + digest(
                    [
                        json.dumps(document, ensure_ascii=False),
                        (ROOT / f"prompts/{PROMPT}.txt").read_text(),
                        evidence_schema(),
                        classifier.cfg,
                    ]
                ),
            }
            store.write(batch, [record("pipeline_runs", batch, ident, label, vid)])
        sample = sampled[vid]
        model = dict(
            label,
            id=ident,
            narratives=[label["primary_narrative"], *label["secondary_narratives"]],
            tier=sample["tier"],
            language=sample.get("language", "und"),
            sampling_country=sample.get("sampling_country"),
        )
        queue = {
            "item_id": ident,
            "item_type": "video",
            "model_label": model,
            "human_label": None,
            "adjudicated_label": None,
            "review_status": "pending",
            "qa_strata": [
                "evidence_revision",
                label["assessment_status"],
                document["scope"],
            ],
            "classifier_version": VERSION,
        }
        store.write(
            batch, [record("human_validation", batch, ident + ":review", queue, vid)]
        )
        outcomes.append(label)
    summary = distribution_report(outcomes)
    summary.update(
        batch=batch,
        classifier_version=VERSION,
        newly_classified=processed,
        pending=len(pending),
        status="partial" if pending else "complete",
        baseline_preserved=True,
        publication="candidate labels are private and require separate validation",
    )
    report = {"reclassification_report": summary, "generated_at": now()}
    store.write(
        batch,
        [
            record(
                "pipeline_runs",
                batch,
                f"{batch}:reclassification-report:{VERSION}:" + digest(report),
                report,
            )
        ],
    )
    return summary


def distribution_report(labels):
    scored = [x for x in labels if x.get("assessment_status") == "scored"]
    return {
        "total": len(labels),
        "scored": len(scored),
        "statuses": dict(Counter(x["assessment_status"] for x in labels)),
        "evidence_scopes": dict(Counter(x["evidence_scope"] for x in labels)),
        "all_zero_scored": sum(all(x[k] == 0 for k in DIMENSIONS) for x in scored),
        "dimension_counts": {
            k: dict(Counter(str(x[k]) for x in scored)) for k in DIMENSIONS
        },
        "abstentions_excluded_from_score_denominators": True,
    }
