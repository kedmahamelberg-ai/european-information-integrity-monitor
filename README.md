# European Information Integrity Monitor

A transcript-based research monitor of conflict and hybrid-threat communication in European YouTube content. It codes topic relevance, portrayed military/security roles, execution style, comment agreement and comment sentiment. The active taxonomy replaces sectarianism; old observations and human reviews remain immutable legacy records.

[Public monitor](https://kedmahamelberg-ai.github.io/european-information-integrity-monitor/) · [Methods](https://kedmahamelberg-ai.github.io/european-information-integrity-monitor/#methodology)

## Evidence rules

- Every included video needs a successfully retrieved English transcript/subtitle track. English audio without saved text is not sufficient. Preserve original language and caption/translation provenance.
- Reclassification uses the frozen source sample, saved captions and retained comments. Caption recovery does not discover new videos or comments.
- Security/sovereignty relevance is related, not related or unclear. Separate current, historical, hypothetical and mixed contexts. Natural-disaster protection and ordinary political criticism alone are not conflict topics.
- Roles are entity-specific, multi-label portrayals: **Defence readiness**, **Force projection & coercion**, **Target of hostile action**. A portrayal or allegation is not verified attribution.
- Execution adapts Dall’Olio & Vakratsas (2022), Table 5: comparative, endorsement, entertainment, imagery/visual and mnemonic devices. Apply only to security-related videos. Transcript-only models cannot code visual execution. This advertising-derived adaptation is not a validated persuasion/effectiveness scale.
- Stance applies only to comments, relative to a named claim, policy, action or narrative in the video content. Neutral videos can receive supportive/opposing comments; sentiment and its target are independent. Original comments and saved English translations stay private.
- Public counters are timestamped views, likes and total comments, with nullable missing values, video age and per-1,000-view ratios. Public shares are unavailable. No combined “engagement” sum or causal claims.
- Minimum available comments: **2**. Existing collection retains up to 30 from a pool of up to 100 visible top-level comments. This is not the full audience.

## Workflows

`Sunday research collection` retains the existing discovery/sample design and feeds the conflict taxonomy. `Transcript-based conflict classification` reuses a specified retained batch and attempts public English caption recovery. It never discovers additional videos or retrieves additional comments. Both share the same single-writer concurrency group and $5 weekly model budget.

The Observatory model policy remains `gpt-5-nano`, switching to `gpt-5.6-luna` at 2026-12-10 00:00 UTC. No expensive fallback is configured. Configuration is in `config/review_models.json`; taxonomy in `config/hybrid.json`; prompts in `prompts/hybrid-framing-1.1.txt`.

```sh
PYTHONPATH=src python -m eiim.hybrid --batch 2026-W40 --retrieve-captions
PYTHONPATH=src python -m eiim.hybrid --collect
PYTHONPATH=src python -m eiim.cli review-import --help
PYTHONPATH=src python -m unittest discover -s tests -q
python scripts/build_site.py --live
```

Production credentials stay in GitHub secrets and server-side service-role RPC calls. The public website is static GitHub Pages. No credentials, raw comments, transcripts or private review files are published. Existing Supabase private tables store versioned payloads; no new paid resource or public raw-data access is required.

## Human review

`eiim.hybrid_review.packet(store, batch)` and `write_html(packet, private_path)` generate the private embedded-video review page. Each video topic, role and execution classification, and each comment stance, target and sentiment classification requires an explicit agree/correct decision. No decisions are pre-confirmed. Exported reviews bind to the immutable source hash and model version and can be imported with the existing review CLI.

Initial calibration requests 30 eligible videos (or the full pool if smaller); later batches use 3%, rounded up, minimum 5. Selection is independent of model outcomes. The new transcript gate creates a new eligible population; legacy review assignments are not repurposed. Comment reviews are optional and separate. A neutral content summary and the English transcript provide reference context; the video has no stance label. Each comment names its own stance target. Existing older classifications and reviews remain immutable under their original version.

The public exporter allows source metadata, engagement counters and individually reviewed video labels. Remaining AI labels stay private until the complete random review assignment is finished and the batch is fully classified, then appear explicitly as AI-coded/sample-audited. Raw discussion remains private. Calibration completion is not proof of reliability; no validated-model accuracy claim is made.

## Research foundations

- [Dall’Olio & Vakratsas — Advertising creative strategy](https://doi.org/10.1177/00222429221074960): five execution categories, adapted descriptively to security content.
- [NATO — Countering hybrid threats](https://www.nato.int/en/what-we-do/deterrence-and-defence/countering-hybrid-threats): scope of military and non-military coercion.
- [Hybrid CoE — Hybrid threats](https://www.hybridcoe.fi/hybrid-threats/): attribution and coordinated-activity limits.
- [Mohammad et al. — SemEval 2016 stance detection](https://aclanthology.org/S16-1003/): stance is distinct from sentiment.
- [YouTube video statistics](https://developers.google.com/youtube/v3/docs/videos#statistics): available public counters.

The country frame, random sampling, inclusion probabilities and original collection timestamps are preserved. Caption availability and visibility-based comment sampling limit generalization. Historical content and current threats must not be pooled without an explicit context filter. Raw observations follow the existing 30-day retention policy.

The execution codebook includes a separately named sixth category, **verbal imagery**, for transcript-evidenced scene-setting. Clear implicit comparisons of institutions, rights or living conditions also qualify; this is an explicit adaptation beyond the paper’s direct-comparison criterion. Two supplied human reviews inform calibration and remain bound to their original version, not counted as fresh independent validation. `--refresh-engagement` refreshes only counters for retained transcript-eligible IDs and preserves original snapshots.
