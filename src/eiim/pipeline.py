"""Restartable Sunday pipeline. Every stage commits atomically in Supabase."""

from collections import defaultdict, Counter
from datetime import datetime, timezone
import json, uuid
from .core import *
from .storage import record
from .services import (
    BudgetExhausted,
    ClassificationUnavailable,
    Ledger,
    YouTube,
    LocalModel,
    Classifier,
)
from .language_access import (
    EnglishCaptionAccess,
    access_records,
    video_access,
    translated_comment,
)
from .research import qa_sample, emerging, validation_gate


class Pipeline:
    def __init__(
        self, store, at=None, youtube=None, local=None, classifier=None, revision=None
    ):
        self.store = store
        self.window = weekly_window(at)
        self.id = self.window["id"]
        self.cfg = config("sampling")
        self.models = config("models")
        self.ledger = Ledger(store, self.id)
        self.yt = youtube
        self.local = local
        self.classifier = classifier
        self.revision = revision
        if revision:
            if not re.fullmatch(r"[a-z0-9-]{1,32}", revision):
                raise ValueError("Revision must be a short lowercase identifier")
            self.base_id = self.id
            self.id = self.id + "--" + revision
            self.window["id"] = self.id
            self.window["supersedes_batch"] = self.base_id
            self.ledger = Ledger(store, self.id)

    def values(self, table, batch=True):
        return [
            r["payload"]
            for r in self.store.read(table, self.id if batch else None)
            if not r.get("purged_at")
        ]

    def records(self, table, rows, key, video_key=None):
        return [
            record(
                table,
                self.id,
                self.id + ":" + str(x[key]),
                x,
                x.get(video_key) if video_key else None,
            )
            for x in rows
        ]

    def cached(self, table, key):
        return {x[key]: x for x in self.values(table)}

    def run(self):
        configs = {
            k: config(k)
            for k in [
                "sampling",
                "countries",
                "channels",
                "models",
                "amplification",
                "narratives",
                "retention",
            ]
        }
        configs["prompt"] = (ROOT / "prompts/sfi-1.0.txt").read_text()
        configs["source_version"] = __import__("eiim").__version__
        batch = self.store.batch(self.window, digest(configs))
        self.window = batch["payload"]
        done = set(batch["completed_stages"])
        if self.revision and not done:
            originals = self.store.read("weekly_batches", self.base_id)
            if (
                not originals
                or "comments_complete" not in originals[0]["completed_stages"]
            ):
                raise ValueError("Correction needs a retained complete source sample")
            copied = []
            for table in [
                "candidate_videos",
                "channels",
                "channel_snapshots",
                "countries",
                "geographic_terms",
                "sampled_videos",
                "comments",
                "comment_embeddings_metadata",
            ]:
                for r in self.store.read(table, self.base_id):
                    if r.get("purged_at"):
                        raise ValueError(
                            "Cannot reclassify expired source observations"
                        )
                    copied.append(
                        record(
                            table,
                            self.id,
                            self.id + r["id"][len(self.base_id) :],
                            r["payload"],
                            r.get("video_id"),
                        )
                    )
            for r in self.store.read("pipeline_runs", self.base_id):
                if "comment_video_id" in r["payload"]:
                    copied.append(
                        record(
                            "pipeline_runs",
                            self.id,
                            self.id + r["id"][len(self.base_id) :],
                            r["payload"],
                            r.get("video_id"),
                        )
                    )
            self.store.write(self.id, copied, "discovery_complete")
            self.store.write(self.id, [], "sampling_complete")
            self.store.write(self.id, [], "comments_complete")
            done.update(
                ["discovery_complete", "sampling_complete", "comments_complete"]
            )
        if "published" in done:
            return {"status": "published", "batch": self.id, "resumed": True}
        self.yt = self.yt or YouTube(self.store, self.id, self.ledger)
        self.local = self.local or LocalModel(self.ledger)
        self.classifier = self.classifier or Classifier(
            self.store, self.id, self.ledger
        )
        try:
            if "discovery_complete" not in done:
                self.discovery()
            if "sampling_complete" not in done:
                self.sampling()
            self.prepare_english_access()
            if "classification_complete" not in done:
                self.classify_videos()
            if "comments_complete" not in done:
                self.comments()
            if "classification_complete" not in done:
                self.classification()
            if "analytics_complete" not in done:
                self.analytics()
            result = validation_gate(
                self.values("human_validation", False),
                self.models["classifier_version"],
            )
            status = "published" if result["passed"] else "awaiting_validation"
            self.store.write(self.id, [], status)
            return {
                "status": status,
                "batch": self.id,
                "validation": result,
                "costs": self.cost_report(),
            }
        except BudgetExhausted:
            self.store.write(self.id, [], "pending_budget")
            return {
                "status": "pending_budget",
                "batch": self.id,
                "costs": self.cost_report(),
            }
        except Exception as error:
            self.store.write(
                self.id,
                [
                    record(
                        "pipeline_errors",
                        self.id,
                        str(uuid.uuid4()),
                        {
                            "at": now(),
                            "error_type": type(error).__name__,
                            "message": "Stage failed; retained checkpoints support restart.",
                        },
                    )
                ],
                "failed",
            )
            raise

    def cost_report(self):
        totals = Counter()
        for e in self.ledger.events():
            totals[e["kind"]] += e["amount"]
        return dict(totals)

    def prepare_english_access(self):
        candidates = self.cached("candidate_videos", "video_id")
        self.access = access_records(self.store.read("pipeline_runs", self.id))
        provider = EnglishCaptionAccess()
        for s in self.values("sampled_videos"):
            vid = s["video_id"]
            if not s["selected_for_sample"] or (self.id, vid) in self.access:
                continue
            p = provider.check(candidates[vid])
            self.store.write(
                self.id,
                [
                    record(
                        "pipeline_runs",
                        self.id,
                        self.id + ":english-access:" + vid + ":" + digest(p),
                        p,
                        vid,
                    )
                ],
            )
            self.access[(self.id, vid)] = p

    def active_samples(self):
        candidates = self.cached("candidate_videos", "video_id")
        access = getattr(self, "access", None)
        if access is None:
            access = access_records(self.store.read("pipeline_runs", self.id))
        return [
            s
            for s in self.values("sampled_videos")
            if s["selected_for_sample"]
            and video_access(candidates[s["video_id"]], self.id, access)["eligible"]
        ]

    def discovery(self):
        ids = self.yt.discover(self.window)
        videos = self.yt.resources("videos", ids, "snippet,statistics,contentDetails")
        chids = sorted(set(v["snippet"]["channelId"] for v in videos))
        channels = self.yt.resources(
            "channels", chids, "snippet,statistics,brandingSettings"
        )
        tiers = {
            x["channel_id"]: x
            for x in channel_tiers(
                channels, datetime.fromisoformat(self.window["collection_timestamp"])
            )
        }
        frame = []
        for v in videos:
            sn = v["snippet"]
            published = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            countries, generic = country_matches(sn["title"], sn.get("description", ""))
            eligible = datetime.fromisoformat(
                self.window["window_start"]
            ) <= published < datetime.fromisoformat(
                self.window["end_exclusive"]
            ) and bool(
                countries or generic
            )
            frame.append(
                {
                    "video_id": v["id"],
                    "title": sn["title"],
                    "description": sn.get("description", ""),
                    "channel_id": sn["channelId"],
                    "channel": sn.get("channelTitle", ""),
                    "published_at": sn["publishedAt"],
                    "countries": countries,
                    "generic_europe": generic,
                    "frame_eligible": eligible,
                    "tier": tiers.get(sn["channelId"], {}).get("tier", "low"),
                    "comment_count": int(
                        v.get("statistics", {}).get("commentCount", 0)
                    ),
                    "category_id": sn.get("categoryId"),
                    "original_audio_language": sn.get("defaultAudioLanguage", "und"),
                    "raw_api_response": v,
                    "retrieved_at": self.window["collection_timestamp"],
                }
            )
        rows = self.records("candidate_videos", frame, "video_id", "video_id")
        rows += self.records(
            "channels", [{"channel_id": c["id"]} for c in channels], "channel_id"
        )
        rows += self.records(
            "channel_snapshots",
            [
                dict(
                    tiers[c["id"]],
                    raw_api_response=c,
                    retrieved_at=self.window["collection_timestamp"],
                )
                for c in channels
            ],
            "channel_id",
        )
        rows += self.records("countries", config("countries")["countries"], "iso2")
        terms = []
        for c in config("countries")["countries"]:
            for t in set(
                [
                    c["country_name"],
                    c["english_demonym"],
                    *c["local_names"],
                    *c["variants"],
                    *c["local_demonyms"],
                    *c["adjectival_forms"],
                ]
            ):
                terms.append(
                    {
                        "id": digest([c["iso2"], t]),
                        "iso2": c["iso2"],
                        "term": t,
                        "version": config("countries")["version"],
                    }
                )
        rows += self.records("geographic_terms", terms, "id")
        for table, cfg in [
            ("classifier_versions", self.models),
            ("taxonomy_versions", config("narratives")),
            (
                "prompt_versions",
                {
                    "version": self.models["prompt_version"],
                    "text": (ROOT / "prompts/sfi-1.0.txt").read_text(),
                },
            ),
        ]:
            rows.append(record(table, self.id, self.id + ":" + digest(cfg), cfg))
        self.store.write(self.id, rows, "discovery_complete")

    def sampling(self):
        frame = []
        cache = {
            x.get("relevance_video_id"): x
            for x in self.values("pipeline_runs")
            if "relevance_video_id" in x
        }
        for v in self.values("candidate_videos"):
            if not v["frame_eligible"]:
                frame.append(
                    dict(
                        v,
                        news_relevance=False,
                        news_relevance_confidence=1,
                        relevance_method="geography_or_window",
                    )
                )
                continue
            text = v["title"] + "\n" + v["description"]
            r = cache.get(v["video_id"])
            if r is None:
                r = self.local.relevance(text, v.get("category_id"))
                lang = self.local.language(text)
                if r["news_relevance"] is None:
                    r = self.classifier.relevance(text)
                r = {
                    **r,
                    "language": lang["language"],
                    "language_confidence": lang["confidence"],
                    "relevance_video_id": v["video_id"],
                }
                self.store.write(
                    self.id,
                    [
                        record(
                            "pipeline_runs",
                            self.id,
                            self.id + ":relevance:" + v["video_id"],
                            r,
                            v["video_id"],
                        )
                    ],
                )
            # Sampling record references raw candidate rather than duplicating the text.
            frame.append(
                {
                    **{
                        k: v[k] for k in ["video_id", "countries", "tier", "channel_id"]
                    },
                    **r,
                }
            )
        sampled = sample_frame(frame, self.id, self.cfg)
        sampled = [
            {
                k: x[k]
                for k in [
                    "video_id",
                    "countries",
                    "tier",
                    "channel_id",
                    "news_relevance",
                    "news_relevance_confidence",
                    "relevance_method",
                    "sampling_country",
                    "sampling_stratum",
                    "sampling_seed",
                    "selected_for_sample",
                    "sampling_probability",
                    "audit_exclusion_sample",
                    "selection_reason",
                ]
                if k in x
            }
            | {"language": x.get("language", "und")}
            for x in sampled
        ]
        selected = sum(x["selected_for_sample"] for x in sampled)
        if selected > self.cfg["max_videos_per_run"]:
            raise ValueError(
                "Sampling target exceeds configured processing ceiling; adjust next batch config"
            )
        audits = [
            {
                "item_id": x["video_id"],
                "item_type": "exclusion",
                "model_label": x,
                "human_label": None,
                "adjudicated_label": None,
                "review_status": "pending",
                "classifier_version": self.models["classifier_version"],
            }
            for x in sampled
            if x["audit_exclusion_sample"]
        ]
        self.store.write(
            self.id,
            self.records("sampled_videos", sampled, "video_id", "video_id")
            + self.records("human_validation", audits, "item_id"),
            "sampling_complete",
        )

    def comments(self, refresh_policy=False, mark_complete=True):
        candidates = self.cached("candidate_videos", "video_id")
        metadata = {}
        for x in self.values("pipeline_runs"):
            if "comment_video_id" in x:
                old = metadata.get(x["comment_video_id"])
                if old is None or x.get("minimum_available_comments", 20) < old.get(
                    "minimum_available_comments", 20
                ):
                    metadata[x["comment_video_id"]] = x
        minimum = self.cfg["minimum_available_comments"]
        for s in self.active_samples():
            if not s["selected_for_sample"]:
                continue
            previous = metadata.get(s["video_id"])
            if previous and (
                not refresh_policy
                or previous.get("retained_count", 0) > 0
                or previous.get("minimum_available_comments", 20) <= minimum
            ):
                continue
            v = candidates[s["video_id"]]
            if previous and v["comment_count"] < minimum:
                continue
            pool, status = (
                self.yt.comments(v["video_id"])
                if v["comment_count"] >= self.cfg["minimum_available_comments"]
                else ([], "below_metadata_threshold")
            )
            retained = rank_comments(pool, self.cfg)
            eligible = len(pool) >= self.cfg["minimum_available_comments"]
            retained = retained if eligible else []
            rows = []
            for c in retained:
                c = {**c, **self.local.language(c["text_original"])}
                c["original_language"] = c["language"]
                c["original_language_confidence"] = c["confidence"]
                rows.append(
                    record(
                        "comments",
                        self.id,
                        self.id + ":" + c["comment_id"],
                        c,
                        v["video_id"],
                    )
                )
            rows.append(
                record(
                    "pipeline_runs",
                    self.id,
                    self.id
                    + ":comment-pool:"
                    + v["video_id"]
                    + (f":min-{minimum}" if refresh_policy else ""),
                    {
                        "comment_video_id": v["video_id"],
                        "pool_size": len(pool),
                        "retained_count": len(retained),
                        "eligible": eligible,
                        "status": status,
                        "minimum_available_comments": minimum,
                        "sampling_version": self.cfg["version"],
                        "retrieved_at": now(),
                    },
                    v["video_id"],
                )
            )
            self.store.write(self.id, rows)
        if mark_complete:
            self.store.write(self.id, [], "comments_complete")

    def classify_videos(self):
        """Make source labels available for review before comment processing finishes."""
        candidates = self.cached("candidate_videos", "video_id")
        classified = self.cached("video_classifications", "video_id")
        for s in self.active_samples():
            if not s["selected_for_sample"]:
                continue
            vid = s["video_id"]
            v = candidates[vid]
            text = v["title"] + "\n" + v["description"]
            if vid not in classified:
                try:
                    result = self.classifier.classify(text)
                except ClassificationUnavailable:
                    p = {
                        "classification_pending_video_id": vid,
                        "status": "classification_unavailable",
                        "checked_at": now(),
                    }
                    self.store.write(
                        self.id,
                        [
                            record(
                                "pipeline_runs",
                                self.id,
                                self.id + ":pending-label:" + vid + ":" + digest(p),
                                p,
                                vid,
                            )
                        ],
                    )
                    continue
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
                payload = {
                    **result["parsed"],
                    **meta,
                    "video_id": vid,
                    "raw_response_ref": self.id
                    + ":model:"
                    + digest(
                        [
                            text,
                            (ROOT / "prompts/sfi-1.0.txt").read_text(),
                            __import__("eiim.services", fromlist=["schema"]).schema(),
                            self.models,
                        ]
                    ),
                }
                rs = self.records(
                    "video_classifications", [payload], "video_id", "video_id"
                )
                for co in payload["countries"]:
                    rs.append(
                        record(
                            "video_country_mentions",
                            self.id,
                            self.id + ":" + vid + ":" + co,
                            {"iso2": co, "basis": "classifier_target", "video_id": vid},
                            vid,
                        )
                    )
                for n in [
                    payload["primary_narrative"],
                    *payload["secondary_narratives"],
                ]:
                    rs.append(
                        record(
                            "video_narratives",
                            self.id,
                            self.id + ":" + vid + ":" + n,
                            {
                                "narrative": n,
                                "video_id": vid,
                                "taxonomy_version": payload["taxonomy_version"],
                            },
                            vid,
                        )
                    )
                for t in payload["targets"]:
                    rs.append(
                        record(
                            "video_targets",
                            self.id,
                            self.id + ":" + vid + ":" + digest(t),
                            t,
                            vid,
                        )
                    )
                self.store.write(self.id, rs)

    def classification(self, classify_sources=True, mark_complete=True):
        cc = self.cached("comment_classifications", "comment_id")
        emb = self.cached("comment_embeddings_metadata", "comment_id")
        comments = defaultdict(list)
        for c in self.values("comments"):
            comments[c["video_id"]].append(c)
        if classify_sources:
            self.classify_videos()
        translations = {
            p["comment_translation_id"]: p
            for p in self.values("pipeline_runs")
            if "comment_translation_id" in p
        }
        for s in self.active_samples():
            if not s["selected_for_sample"]:
                continue
            vid = s["video_id"]
            cs = sorted(comments[vid], key=lambda c: c["comment_id"])
            if not cs:
                continue
            for c in cs:
                if c["comment_id"] not in translations:
                    p = translated_comment(c, self.classifier)
                    self.store.write(
                        self.id,
                        [
                            record(
                                "pipeline_runs",
                                self.id,
                                self.id + ":translation-en:" + c["comment_id"],
                                p,
                                vid,
                            )
                        ],
                    )
                    translations[c["comment_id"]] = p
            missing = [c for c in cs if c["comment_id"] not in emb]
            if missing:
                vs = self.local.embed([c["text_original"] for c in missing])
                ers = []
                for c, vec in zip(missing, vs):
                    p = {
                        "comment_id": c["comment_id"],
                        "video_id": vid,
                        "vector": vec,
                        "embedding_model": self.models["embedding_model"],
                        "text_hash": digest(c["text_normalized"]),
                    }
                    emb[c["comment_id"]] = p
                    ers.append(
                        record(
                            "comment_embeddings_metadata",
                            self.id,
                            self.id + ":" + c["comment_id"],
                            p,
                            vid,
                        )
                    )
                self.store.write(self.id, ers)
            vectors = [emb[c["comment_id"]]["vector"] for c in cs]
            groups = coherent_clusters(
                vectors, config("amplification")["near_duplicate_similarity"], 1
            )
            for g in groups:
                representative = cs[g[0]]
                label = cc.get(representative["comment_id"])
                if label is None:
                    result = self.classifier.classify(
                        translations[representative["comment_id"]]["text_english"]
                    )
                    label = {
                        "label_language": "en",
                        "original_language": representative.get(
                            "original_language", representative.get("language", "und")
                        ),
                        "translation_status": translations[
                            representative["comment_id"]
                        ]["translation_status"],
                        **result["parsed"],
                        **{
                            k: result[k]
                            for k in [
                                "model_version",
                                "prompt_version",
                                "taxonomy_version",
                                "classifier_version",
                                "classification_timestamp",
                            ]
                        },
                    }
                rs = []
                for i in g:
                    c = cs[i]
                    if c["comment_id"] in cc:
                        continue
                    p = {
                        **label,
                        "comment_id": c["comment_id"],
                        "original_language": c.get(
                            "original_language", c.get("language", "und")
                        ),
                        "translation_status": translations[c["comment_id"]][
                            "translation_status"
                        ],
                        "label_source_original_language": representative.get(
                            "original_language", representative.get("language", "und")
                        ),
                        "video_id": vid,
                        "representative_comment_id": representative["comment_id"],
                        "propagation_method": (
                            "direct" if i == g[0] else "complete_link_near_duplicate"
                        ),
                    }
                    cc[c["comment_id"]] = p
                    rs.append(
                        record(
                            "comment_classifications",
                            self.id,
                            self.id + ":" + c["comment_id"],
                            p,
                            vid,
                        )
                    )
                self.store.write(self.id, rs)
        if mark_complete:
            self.store.write(self.id, [], "classification_complete")

    def analytics(self):
        vs = self.cached("candidate_videos", "video_id")
        labels = self.cached("video_classifications", "video_id")
        active = {s["video_id"] for s in self.active_samples()}
        labels = {vid: label for vid, label in labels.items() if vid in active}
        samples = self.cached("sampled_videos", "video_id")
        cl = self.cached("comment_classifications", "comment_id")
        emb = self.cached("comment_embeddings_metadata", "comment_id")
        comments = defaultdict(list)
        all_comments = [c for c in self.values("comments") if c["video_id"] in labels]
        for c in all_comments:
            comments[c["video_id"]].append(c)
        recgroups = defaultdict(list)
        for c in all_comments:
            recgroups[digest(normalize(c["text_original"]))].append(c)
        # Local nearest-neighbour candidates; all final recurrence groups require complete-link coherence.
        if len(all_comments) > 1 and self.models.get("semantic_cross_video", True):
            vectors = [emb[c["comment_id"]]["vector"] for c in all_comments]
            if len(vectors) < 500:
                nearest = [
                    sorted([(1 - cosine(a, b), j) for j, b in enumerate(vectors)])[:8]
                    for a in vectors
                ]
                dist = [[d for d, j in row] for row in nearest]
                idx = [[j for d, j in row] for row in nearest]
            else:
                from sklearn.neighbors import NearestNeighbors

                nn = NearestNeighbors(n_neighbors=8, metric="cosine").fit(vectors)
                dist, idx = nn.kneighbors(vectors)
            for i, (ds, js) in enumerate(zip(dist, idx)):
                group = [
                    int(j)
                    for d, j in zip(ds, js)
                    if d <= 1 - config("amplification")["near_duplicate_similarity"]
                ]
                if len(group) > 1 and all(
                    cosine(vectors[a], vectors[b])
                    >= config("amplification")["near_duplicate_similarity"]
                    for a in group
                    for b in group
                ):
                    recgroups[
                        digest(sorted(all_comments[j]["comment_id"] for j in group))
                    ] = [all_comments[j] for j in group]
        recurrence = []
        recurring = set()
        seen = set()
        for g in recgroups.values():
            ids = sorted(set(c["comment_id"] for c in g))
            key = digest(ids)
            if len(set(c["video_id"] for c in g)) < 2 or key in seen:
                continue
            seen.add(key)
            recurring.update(ids)
            vids = {c["video_id"] for c in g}
            recurrence.append(
                {
                    "id": key,
                    "comment_ids": ids,
                    "video_count": len(vids),
                    "channel_count": len({vs[v]["channel_id"] for v in vids}),
                    "country_count": len(
                        {co for v in vids for co in labels[v]["countries"]}
                    ),
                    "comment_count": len(ids),
                    "first_seen": min(c["published_at"] for c in g),
                    "last_seen": max(c["published_at"] for c in g),
                    "search_note": "Exact matches plus up to eight local nearest-neighbour candidates per comment; bounded near-template search.",
                }
            )
        rows = self.records("cross_video_clusters", recurrence, "id")
        public = []
        comment_pools = {
            x["comment_video_id"]: x
            for x in self.values("pipeline_runs")
            if "comment_video_id" in x
        }
        cluster_reviews = []
        for vid, label in labels.items():
            v = vs[vid]
            s = samples[vid]
            cs = sorted(comments[vid], key=lambda c: c["comment_id"])
            aai = None
            inj = None
            ns = [label["primary_narrative"], *label["secondary_narratives"]]
            if cs:
                vectors = [emb[c["comment_id"]]["vector"] for c in cs]
                source = self.local.embed([v["title"] + "\n" + v["description"]])[0]
                groups = coherent_clusters(
                    vectors,
                    config("amplification")["coherent_similarity"],
                    config("amplification")["cluster_min_size"],
                )
                clusterlabels = {}
                for i, g in enumerate(groups):
                    clusterlabels[i] = [
                        Counter(
                            cl[cs[j]["comment_id"]]["primary_narrative"] for j in g
                        ).most_common(1)[0][0]
                    ]
                inj = injection(groups, source, vectors, ns, clusterlabels)
                aai = amplification(
                    cs,
                    vectors,
                    [cl[c["comment_id"]]["primary_narrative"] for c in cs],
                    source,
                    recurring,
                )
                rows.append(
                    record(
                        "narrative_injection_results",
                        self.id,
                        self.id + ":" + vid,
                        {"video_id": vid, **inj},
                        vid,
                    )
                )
                rows.append(
                    record(
                        "amplification_signals",
                        self.id,
                        self.id + ":" + vid,
                        {
                            "video_id": vid,
                            **aai,
                            "amplification_version": config("amplification")["version"],
                        },
                        vid,
                    )
                )
                for i, g in enumerate(inj["clusters"]):
                    cid = vid + ":" + str(i)
                    payload = {
                        "id": cid,
                        "video_id": vid,
                        **g,
                        "comment_ids": [cs[j]["comment_id"] for j in g["members"]],
                    }
                    rows.append(
                        record(
                            "comment_clusters",
                            self.id,
                            self.id + ":" + cid,
                            payload,
                            vid,
                        )
                    )
                    cluster_reviews.append(
                        {
                            "item_id": cid,
                            "item_type": "comment_cluster",
                            "model_label": payload,
                            "human_label": None,
                            "adjudicated_label": None,
                            "review_status": "pending",
                            "classifier_version": self.models["classifier_version"],
                        }
                    )
            pool = comment_pools.get(vid, {})
            p = {
                "id": self.id + ":" + vid,
                "video_id": vid,
                "batch": self.id,
                "title": v["title"],
                "channel": v["channel"],
                "channel_id": v["channel_id"],
                "published_at": v["published_at"],
                "countries": label["countries"],
                "tier": s["tier"],
                "language": s["language"],
                "original_audio_language": video_access(v, self.id, self.access)[
                    "original_language"
                ],
                "english_access_status": video_access(v, self.id, self.access)[
                    "status"
                ],
                "language_policy_version": video_access(v, self.id, self.access)[
                    "policy_version"
                ],
                "sfi": label["sfi"],
                "othering": label["othering"],
                "aversion": label["aversion"],
                "moralization": label["moralization"],
                "confidence": label["confidence"],
                "narratives": ns,
                "targets": [t["target_name"] for t in label["targets"]],
                "rationale": label["short_rationale"],
                "aai": aai["aai"] if aai else None,
                "aai_components": aai["components"] if aai else {},
                "comments_analyzed": len(cs),
                "comment_pool_size": pool.get("pool_size", 0),
                "injection": inj["narrative_injection_score"] if inj else None,
                "injected_comments": inj["injected_comments"] if inj else 0,
                "excerpts": [],
                "sampling_country": s["sampling_country"],
                "stratum": s["sampling_stratum"],
                "sampling_probability": s["sampling_probability"],
                "sampling_seed": s["sampling_seed"],
                **{
                    k: label[k]
                    for k in [
                        "model_version",
                        "prompt_version",
                        "taxonomy_version",
                        "classifier_version",
                    ]
                },
            }
            public.append(p)
        qa = qa_sample(public, self.cfg["seed"])
        qa = [dict(q, classifier_version=self.models["classifier_version"]) for q in qa]
        cluster_reviews = sorted(
            cluster_reviews, key=lambda r: digest([self.cfg["seed"], r["item_id"]])
        )[:20]
        rows += self.records("human_validation", qa + cluster_reviews, "item_id")
        # Compare OTHER labels with preserved preceding weekly classifications.
        batches = {b["id"]: b["payload"] for b in self.store.read("weekly_batches")}
        other = []
        emerg = []
        for row in self.store.read("video_classifications"):
            x = row["payload"]
            if x.get("other_narrative_label") and row["batch_id"] in batches:
                other.append(
                    {
                        "id": row["id"],
                        "label": x["other_narrative_label"],
                        "week_start": batches[row["batch_id"]]["window_start"],
                    }
                )
        if other:
            emerg = emerging(other, self.local.embed([x["label"] for x in other]))
            rows += [
                record(
                    "emerging_narratives",
                    self.id,
                    self.id + ":" + digest(e["item_ids"]),
                    e,
                )
                for e in emerg
            ]
        snapshot = {
            "videos": public,
            "candidates": [
                {
                    "id": v["video_id"],
                    "batch": self.id,
                    "countries": v["countries"],
                    "tier": v["tier"],
                }
                for v in vs.values()
            ],
            "batch": self.window,
            "mode": "live",
            "emerging_narratives": emerg,
            "validation": {"videos_reviewed": 0, "clusters_reviewed": 0},
        }
        rows.append(record("dashboard_snapshots", self.id, self.id, snapshot))
        self.store.write(self.id, rows, "analytics_complete")
