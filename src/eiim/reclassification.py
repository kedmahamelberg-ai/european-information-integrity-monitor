"""Evidence-grounded candidate labels, separate from frozen analytical baselines."""

import copy
import json
from collections import Counter

from .core import ROOT, config, digest, now, validate_classification
from .language_access import access_records, video_access
from .storage import record

from .model_policy import selected_policy

VERSION = "classifier-1.4.2-" + selected_policy()["model"]
PROMPT = "sfi-1.3.3"
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


def evidence_schema(allow_abstention=True):
    from .services import schema

    shape = schema()
    props = shape["properties"]
    for k in DIMENSIONS:
        props[k] = {"type": ["integer", "null"], "minimum": 0, "maximum": 6}
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
    if not allow_abstention:
        props["assessment_status"]["enum"] = ["scored"]
        props["public_affairs_relevance"]["enum"] = ["in_scope"]
        for k in DIMENSIONS:
            props[k]["type"] = "integer"
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
    validated = validate_classification(check, score_max=6)
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
        if quote and quote not in sections.get(e["source_id"], ""):
            # Caption sentences often span several line IDs. Repair the locator
            # only when the exact unchanged quote exists in supplied evidence.
            matches = [key for key, text in sections.items() if quote in text]
            if matches:
                e["model_source_id"] = e["source_id"]
                e["source_id"] = "transcript" if "transcript" in matches else matches[0]
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
        score_max=6,
        sfi=validated["sfi"] if status == "scored" else None,
        strong_sectarian_frame=(
            validated["strong_sectarian_frame"] if status == "scored" else None
        ),
    )


def configure_candidate(classifier):
    classifier.cfg = dict(
        classifier.cfg,
        **selected_policy(),
        classifier_version=VERSION,
        prompt_version=PROMPT,
    )
    return classifier


def classify_document(classifier, document):
    screen_document = dict(
        document,
        sections=[
            s for s in document["sections"] if not s["id"].startswith("transcript:")
        ],
    )
    screen_prompt = (ROOT / "prompts/source-screen-1.1.txt").read_text()
    screen_shape = source_screen_schema()
    screen_text = json.dumps(screen_document, ensure_ascii=False)
    screened = classifier.request(
        screen_text, screen_prompt, screen_shape, "source_screen"
    )
    decision = screened["parsed"]
    screen_ref = (
        classifier.batch
        + ":model:"
        + digest([screen_text, screen_prompt, screen_shape, classifier.cfg])
    )
    if decision["assessment_status"] != "scored":
        parsed = {
            **{k: None for k in DIMENSIONS},
            "sfi": None,
            "strong_sectarian_frame": None,
            "assessment_status": decision["assessment_status"],
            "public_affairs_relevance": (
                "out_of_scope"
                if decision["assessment_status"] == "out_of_scope"
                else "unclear"
            ),
            "publisher_stance": "unclear",
            "targets": [],
            "countries": [],
            "direction": "unclear",
            "primary_narrative": "none_unclear",
            "secondary_narratives": [],
            "other_narrative_label": None,
            "other_narrative_explanation": None,
            "confidence": decision["confidence"],
            "narrative_confidence": 0,
            "short_rationale": decision["explanation"],
            "dimension_evidence": [
                dict(
                    dimension=k,
                    quote="",
                    source_id="",
                    target="",
                    speaker="",
                    attribution="none",
                    explanation=decision["explanation"],
                )
                for k in DIMENSIONS
            ],
        }
        result = dict(
            screened, parsed=parsed, prompt_version=PROMPT, raw_response_ref=screen_ref
        )
    else:
        prompt = (ROOT / f"prompts/{PROMPT}.txt").read_text()
        shape = evidence_schema(allow_abstention=False)
        text = json.dumps(document, ensure_ascii=False)
        result = classifier.request(text, prompt, shape, "sfi_review")
        result = dict(
            result,
            raw_response_ref=classifier.batch
            + ":model:"
            + digest([text, prompt, shape, classifier.cfg]),
        )
    # Independently check cross-dimension leakage without showing initial scores.
    if decision["assessment_status"] == "scored":
        initial = copy.deepcopy(result["parsed"])
        revised = copy.deepcopy(initial)
        audits = {}
        for dimension in ("othering", "aversion"):
            if initial[dimension] <= 0:
                continue
            audit_prompt = (ROOT / f"prompts/cue-check-{dimension}-1.0.txt").read_text()
            audit_text = json.dumps(screen_document, ensure_ascii=False)
            audit_result = classifier.request(
                audit_text, audit_prompt, cue_check_schema(), "cue_check"
            )
            audit = audit_result["parsed"]
            audits[dimension] = dict(
                audit,
                response_ref=classifier.batch
                + ":model:"
                + digest(
                    [audit_text, audit_prompt, cue_check_schema(), classifier.cfg]
                ),
            )
            if not audit["supported"]:
                revised[dimension] = 0
                e = next(
                    e
                    for e in revised["dimension_evidence"]
                    if e["dimension"] == dimension
                )
                e.update(
                    quote="",
                    source_id="",
                    explanation="Independent cue check: " + audit["explanation"],
                )
        revised = validate_evidence_label(revised, document)
        revised.update(
            dimension_audits=audits,
            pre_audit_scores={k: initial[k] for k in DIMENSIONS},
        )
        if any(revised[k] != initial[k] for k in DIMENSIONS):
            revised["pre_audit_rationale"] = initial["short_rationale"]
            revised["short_rationale"] = "After independent cue checks: " + "; ".join(
                e["dimension"]
                + "="
                + str(revised[e["dimension"]])
                + ": "
                + e["explanation"]
                for e in revised["dimension_evidence"]
            )

        result = dict(result, parsed=revised)
    result["parsed"] = dict(
        result["parsed"],
        score_max=6,
        source_screen=decision,
        source_screen_response_ref=screen_ref,
    )
    return result


def cue_check_schema():
    props = {
        "supported": {"type": "boolean"},
        **{k: {"type": "string"} for k in ("quote", "source_id", "explanation")},
    }
    return dict(
        type="object",
        properties=props,
        required=list(props),
        additionalProperties=False,
    )


def validate_cue_check(parsed, document):
    if type(parsed.get("supported")) is not bool:
        raise ValueError("Cue support must be a boolean")
    checked = validate_source_screen(
        dict(
            assessment_status=(
                "scored" if parsed["supported"] else "insufficient_evidence"
            ),
            explanation=parsed.get("explanation"),
            evidence_quote=parsed.get("quote"),
            source_id=parsed.get("source_id"),
            confidence=1,
        ),
        document,
    )
    return dict(parsed, source_id=checked["source_id"])


def source_screen_schema():
    properties = {
        "assessment_status": {
            "type": "string",
            "enum": ["scored", "insufficient_evidence", "out_of_scope"],
        },
        "explanation": {"type": "string"},
        "evidence_quote": {"type": "string"},
        "source_id": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def validate_source_screen(parsed, document):
    if (
        parsed.get("assessment_status")
        not in {"scored", "insufficient_evidence", "out_of_scope"}
        or not isinstance(parsed.get("explanation"), str)
        or not parsed["explanation"].strip()
    ):
        raise ValueError("Invalid source-screen decision")
    quote = parsed.get("evidence_quote")
    if not isinstance(quote, str) or len(quote) > 400:
        raise ValueError("Source-screen quote must be a short exact passage")
    sections = {s["id"]: s["text"] for s in document["sections"]}
    if quote and quote not in sections.get(parsed.get("source_id"), ""):
        matches = [k for k, text in sections.items() if quote in text]
        if not matches:
            raise ValueError(
                "Source-screen quote must exactly match supplied text; no paraphrases or ellipses"
            )
        parsed = dict(parsed, model_source_id=parsed["source_id"], source_id=matches[0])
    if parsed["assessment_status"] == "scored" and not quote:
        raise ValueError("An assessable source needs a quoted substantive proposition")
    if (
        type(parsed.get("confidence")) not in (int, float)
        or not 0 <= parsed["confidence"] <= 1
    ):
        raise ValueError("Invalid source-screen confidence")
    return parsed


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
                evidence_schema(allow_abstention=False),
                (ROOT / "prompts/source-screen-1.1.txt").read_text(),
                source_screen_schema(),
                [
                    (ROOT / f"prompts/cue-check-{d}-1.0.txt").read_text()
                    for d in ("othering", "aversion")
                ],
                cue_check_schema(),
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
                "baseline_score_max": 4,
                "baseline_record_id": originals.get(vid, {}).get("id"),
                "baseline_scores": {
                    k: originals.get(vid, {}).get("payload", {}).get(k)
                    for k in DIMENSIONS
                },
                "raw_response_ref": result.get("raw_response_ref"),
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
            "score_max": 6,
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
