"""Apply confirmed government reviews to retained and public checkpoints."""

import hashlib
import json


SOURCE_FIELDS = (
    "url", "title", "published_at", "english_summary",
    "source_text_chars", "translated_text_chars",
)
REVIEW_FIELDS = (
    "roles", "viewpoint_structure", "viewpoints", "evidence_status",
    "evidence_quote", "short_rationale", "ticker_message",
)


def source_fingerprint(item):
    """Bind a review to the saved source evidence, independent of AI labels."""
    source = {key: item.get(key) for key in SOURCE_FIELDS}
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_confirmed_corrections(items, corrections):
    """Mutate matching items and return (applied IDs, stale IDs)."""
    by_id = {correction["id"]: correction for correction in corrections
             if correction.get("id")}
    applied, stale = [], []
    for item in items:
        correction = by_id.get(item.get("id"))
        if not correction:
            continue
        fingerprint = correction.get("source_fingerprint")
        if fingerprint and fingerprint != source_fingerprint(item):
            stale.append(item["id"])
            continue
        if "relevance" in correction:
            item["relevance"] = correction["relevance"]
        elif "related" in correction:
            item["relevance"] = "related" if correction["related"] else "not_related"
        if "topics" in correction:
            item["topics"] = correction["topics"]
        elif "primary_narrative" in correction:
            item["topics"] = ([correction["primary_narrative"],
                               *correction.get("secondary_narratives", [])]
                              if correction.get("related") else [])
        for key in REVIEW_FIELDS:
            if key in correction:
                item[key] = correction[key]
        topics = item.get("topics") or []
        item.update({
            "related": item.get("relevance") == "related",
            "primary_narrative": topics[0] if topics else "none_unclear",
            "secondary_narratives": topics[1:],
            "classification_status": "human_reviewed",
            "human_reviewed": True,
        })
        applied.append(item["id"])
    return applied, stale
