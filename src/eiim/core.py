"""Pure, versioned measurement and sampling functions. No network or paid inference."""

from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib, json, math, random, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def config(name):
    return json.loads((ROOT / "config" / f"{name}.json").read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def weekly_window(at=None):
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("Timezone-aware collection timestamp required")
    local = at.astimezone(ZoneInfo("Europe/Amsterdam"))
    end = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=(local.weekday() + 1) % 7
    )
    start = end - timedelta(days=7)
    inclusive = end - timedelta(seconds=1)
    return {
        "id": inclusive.strftime("%G-W%V"),
        "window_start": start.isoformat(),
        "window_end": inclusive.isoformat(),
        "end_exclusive": end.isoformat(),
        "collection_timestamp": at.isoformat(),
        "timezone": "Europe/Amsterdam",
    }


def normalize(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).casefold()).strip()


def term_match(text, term):
    return bool(
        re.search(r"(?<!\w)" + re.escape(normalize(term)) + r"(?!\w)", normalize(text))
    )


def country_matches(title, description, cfg=None):
    cfg = cfg or config("countries")
    text = title + "\n" + description
    matched = []
    for c in cfg["countries"]:
        terms = [
            c["country_name"],
            c["english_demonym"],
            *c["local_names"],
            *c["variants"],
            *c["local_demonyms"],
            *c["adjectival_forms"],
        ]
        if any(term_match(text, t) for t in terms):
            matched.append(c["iso2"])
    generic = any(term_match(text, t) for t in cfg["generic_terms"])
    return matched, generic


def sfi(o, a, m, score_max=4):
    if score_max not in (4, 6):
        raise ValueError("Unsupported score scale")
    if any(type(v) is not int or not 0 <= v <= score_max for v in (o, a, m)):
        raise ValueError(f"Dimensions must be integer 0–{score_max}")
    return (o + a + m) / 3, all(v >= score_max / 2 for v in (o, a, m))


def validate_classification(raw, score_max=4):
    x = json.loads(raw) if isinstance(raw, str) else raw
    required = {
        "othering",
        "aversion",
        "moralization",
        "targets",
        "countries",
        "direction",
        "primary_narrative",
        "secondary_narratives",
        "other_narrative_label",
        "other_narrative_explanation",
        "confidence",
        "narrative_confidence",
        "short_rationale",
    }
    if not isinstance(x, dict) or not required <= x.keys():
        raise ValueError("Missing structured classification fields")
    score, strong = sfi(x["othering"], x["aversion"], x["moralization"], score_max)
    for key in ["confidence", "narrative_confidence"]:
        if (
            type(x[key]) not in (int, float)
            or not math.isfinite(x[key])
            or not 0 <= x[key] <= 1
        ):
            raise ValueError("Confidence out of range")
    if x["direction"] not in ["negative", "positive", "mixed", "unclear"]:
        raise ValueError("Invalid direction")
    if x["direction"] == "positive" and score:
        raise ValueError("Positive treatment cannot count as sectarian framing")
    labels = config("narratives")["labels"]
    if not isinstance(x["secondary_narratives"], list) or any(
        n not in labels for n in [x["primary_narrative"], *x["secondary_narratives"]]
    ):
        raise ValueError("Unknown narrative")
    if "other" in [x["primary_narrative"], *x["secondary_narratives"]] and not all(
        isinstance(x[k], str) and x[k].strip()
        for k in ["other_narrative_label", "other_narrative_explanation"]
    ):
        raise ValueError("OTHER requires a label and explanation")
    if not isinstance(x["targets"], list):
        raise ValueError("Targets must be a list")
    for t in x["targets"]:
        if (
            not isinstance(t, dict)
            or not all(
                isinstance(t.get(k), str) and t[k]
                for k in ["target_type", "target_name", "direction"]
            )
            or t["direction"] not in ["negative", "positive", "mixed", "unclear"]
        ):
            raise ValueError("Invalid target")
    if score and not any(t["direction"] in ["negative", "mixed"] for t in x["targets"]):
        raise ValueError("Nonzero framing requires a negative/mixed target")
    valid = {c["iso2"] for c in config("countries")["countries"]}
    if not isinstance(x["countries"], list) or any(
        c not in valid for c in x["countries"]
    ):
        raise ValueError("Invalid target country")
    if not isinstance(x["short_rationale"], str):
        raise ValueError("Rationale required")
    return dict(x, sfi=score, strong_sectarian_frame=strong)


def allocate(n, weights):
    if (
        n < 0
        or not weights
        or any(v < 0 for v in weights.values())
        or not math.isclose(sum(weights.values()), 1)
    ):
        raise ValueError("Invalid allocation")
    result = {k: math.floor(n * w) for k, w in weights.items()}
    order = sorted(weights, key=lambda k: (-(n * weights[k] - result[k]), k))
    for k in order[: n - sum(result.values())]:
        result[k] += 1
    return result


def sample_frame(frame, batch_id, cfg=None):
    cfg = cfg or config("sampling")
    seed = cfg["seed"]
    groups = defaultdict(list)
    out = []
    for x in sorted(frame, key=lambda x: x["video_id"]):
        countries = sorted(set(x["countries"]))
        # Generic Europe records have a separate EU stratum; no fabricated country.
        country = (
            min(countries, key=lambda c: digest([seed, batch_id, x["video_id"], c]))
            if countries
            else "EU"
        )
        item = dict(
            x,
            sampling_country=country,
            sampling_stratum=f"{country}:{x['tier']}",
            sampling_seed=seed,
            selected_for_sample=False,
            sampling_probability=0.0,
            audit_exclusion_sample=False,
            selection_reason="not_eligible",
        )
        if x.get("news_relevance") is True:
            groups[item["sampling_stratum"]].append(item)
        elif x.get("news_relevance") is False:
            item["audit_exclusion_sample"] = (
                int(digest([seed, batch_id, x["video_id"], "audit"])[:16], 16) / 16**16
                < cfg["audit_exclusion_fraction"]
            )
            item["selection_reason"] = "excluded_relevance"
        else:
            item["selection_reason"] = "relevance_pending"
        out.append(item)
    quota = allocate(cfg["target_per_country"], cfg["tier_weights"])
    for key, items in groups.items():
        n = min(len(items), quota[key.split(":")[1]])
        rng = random.Random(digest([seed, batch_id, key]))
        chosen = {x["video_id"] for x in rng.sample(items, n)}
        for x in items:
            x.update(
                sampling_probability=n / len(items),
                selected_for_sample=x["video_id"] in chosen,
                selection_reason=(
                    "random_within_stratum" if x["video_id"] in chosen else "not_drawn"
                ),
            )
    return out


def channel_tiers(channels, at, cfg=None):
    cfg = cfg or config("channels")
    result = []
    for c in channels:
        sn = c.get("snippet", {})
        st = c.get("statistics", {})
        age = None
        if sn.get("publishedAt"):
            age = max(
                0,
                (
                    at
                    - datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
                ).days
                / 365.25,
            )
        uploads = int(st["videoCount"]) if "videoCount" in st else None
        values = {
            "age_years": age,
            "subscribers": (
                None
                if st.get("hiddenSubscriberCount") or "subscriberCount" not in st
                else int(st["subscriberCount"])
            ),
            "uploads": uploads,
            "publishing_frequency": (
                uploads / (age * 365.25) if uploads is not None and age else None
            ),
            "external_domain": int(
                bool(re.search(r"https?://[^\s]+", sn.get("description", "")))
            ),
        }
        den = sum(cfg["weights"][k] for k, v in values.items() if v is not None)
        score = (
            sum(
                cfg["weights"][k]
                * min(1, math.log1p(v) / math.log1p(cfg["log_caps"][k]))
                for k, v in values.items()
                if v is not None
            )
            / den
            if den
            else 0
        )
        result.append(
            {
                "channel_id": c["id"],
                "score": score,
                "components": values,
                "missing_fields": [k for k, v in values.items() if v is None],
                "public_description": sn.get("description", ""),
                "organization_identifiable": None,
                "official_indicator": None,
                "specialization": None,
            }
        )
    scores = sorted(x["score"] for x in result)
    for x in result:
        # Equal score ties stay in the same tier; ratios can differ from thirds.
        q = sum(v < x["score"] for v in scores) / max(1, len(scores))
        x["tier"] = "low" if q < 1 / 3 else "medium" if q < 2 / 3 else "high"
    return result


def rank_comments(comments, cfg=None):
    cfg = cfg or config("sampling")
    weights = cfg["comment_visibility_weights"]
    likes = max([c["like_count"] for c in comments] + [1])
    replies = max([c["reply_count"] for c in comments] + [1])
    out = [
        dict(
            c,
            visibility_score=weights["likes"] * c["like_count"] / likes
            + weights["replies"] * c["reply_count"] / replies,
        )
        for c in comments
    ]
    out.sort(key=lambda c: (-c["visibility_score"], c["comment_id"]))
    n = cfg["comments_per_video"]
    return out if n == "all" else out[:n]


def cosine(a, b):
    den = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return max(-1, min(1, sum(x * y for x, y in zip(a, b)) / den)) if den else 0


def coherent_clusters(vectors, threshold=0.78, min_size=3):
    """Deterministic complete-link greedy clustering: every member clears threshold."""
    clusters = []
    for i, v in enumerate(vectors):
        group = next(
            (g for g in clusters if all(cosine(v, vectors[j]) >= threshold for j in g)),
            None,
        )
        if group is None:
            clusters.append([i])
        else:
            group.append(i)
    return [g for g in clusters if len(g) >= min_size]


def injection(groups, source_vector, vectors, source_labels, cluster_labels, cfg=None):
    cfg = cfg or config("amplification")
    injected = set()
    detail = []
    src = set(source_labels) - {"none_unclear"}
    for index, g in enumerate(groups):
        centroid = [
            sum(vectors[i][d] for i in g) / len(g) for d in range(len(source_vector))
        ]
        sim = cosine(source_vector, centroid)
        labels = set(cluster_labels.get(index, [])) - {"none_unclear", "other"}
        different = bool(labels and src and labels.isdisjoint(src))
        qualifying = (
            len(g) >= cfg["cluster_min_size"]
            and sim < cfg["off_topic_similarity"]
            and different
        )
        if qualifying:
            injected.update(g)
        detail.append(
            {
                "members": g,
                "topic_similarity": sim,
                "off_topic_probability": max(0, 1 - sim),
                "narrative_alignment": not different,
                "qualifies": qualifying,
                "narratives": sorted(labels),
            }
        )
    return {
        "narrative_injection_score": len(injected) / len(vectors) if vectors else None,
        "injected_comments": len(injected),
        "number_of_injected_clusters": sum(x["qualifies"] for x in detail),
        "clusters": detail,
        "dominant_injected_narrative": next(
            (
                x["narratives"][0]
                for x in sorted(detail, key=lambda x: -len(x["members"]))
                if x["qualifies"]
            ),
            None,
        ),
    }


def amplification(
    comments, vectors, narratives, source_vector, recurring_ids=None, cfg=None
):
    cfg = cfg or config("amplification")
    n = len(comments)
    if not n:
        return None
    groups = coherent_clusters(vectors, cfg["near_duplicate_similarity"], 2)
    exact = defaultdict(list)
    for i, c in enumerate(comments):
        exact[normalize(c["text_original"])].append(i)
    groups += [g for g in exact.values() if len(g) > 1]
    groups = [list(g) for g in sorted(set(tuple(sorted(g)) for g in groups))]
    duplicate = set(i for g in groups for i in g)
    largest = max([len(g) for g in groups] + [0])
    times = sorted(
        datetime.fromisoformat(c["published_at"].replace("Z", "+00:00")).timestamp()
        for c in comments
    )
    span = cfg["burst_window_minutes"] * 60
    burst = max(sum(t <= u <= t + span for u in times) for t in times)
    counts = Counter(narratives)
    hhi = sum((v / n) ** 2 for v in counts.values())
    concentration = (hhi - 1 / n) / (1 - 1 / n) if n > 1 else 0
    components = {
        "duplicate_similarity": len(duplicate) / n,
        "temporal_burstiness": max(0, (burst - 1) / max(1, n - 1)),
        "cross_video_recurrence": sum(
            c["comment_id"] in (recurring_ids or set()) for c in comments
        )
        / n,
        "topic_divergence": sum(
            cosine(source_vector, v) < cfg["off_topic_similarity"] for v in vectors
        )
        / n,
        "narrative_concentration": max(0, min(1, concentration)),
    }
    if not math.isclose(sum(cfg["weights"].values()), 1):
        raise ValueError("AAI weights must sum to one")
    return {
        "aai": sum(components[k] * w for k, w in cfg["weights"].items()),
        "components": components,
        "duplicate_comment_share": len(duplicate) / n,
        "near_duplicate_cluster_count": len(groups),
        "largest_duplicate_cluster_share": largest / n,
        "burst_score": components["temporal_burstiness"],
        "largest_burst_size": burst,
        "burst_window_minutes": cfg["burst_window_minutes"],
        "denominator": n,
    }
