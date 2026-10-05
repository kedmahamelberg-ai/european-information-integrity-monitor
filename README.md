# European Information Integrity Monitor

A transcript-based research monitor of conflict and hybrid-threat communication in European YouTube content. It codes topic relevance, portrayed military/security roles, execution style, comment agreement and comment sentiment. The active taxonomy replaces sectarianism; old observations and human reviews remain immutable legacy records.

[Public monitor](https://kedmahamelberg-ai.github.io/european-information-integrity-monitor/) · [Methods](https://kedmahamelberg-ai.github.io/european-information-integrity-monitor/#methodology)

## Evidence rules

- Every included video needs a successfully retrieved English transcript/subtitle track. English audio without saved text is not sufficient. Preserve original language and caption/translation provenance.
- Reclassification uses the frozen source sample, saved captions and retained comments. Caption recovery does not discover new videos or comments.
- Security/resource/sovereignty relevance is related, not related or unclear. Topics include water, energy, food security and other essential resource dependencies as well as military and hybrid threats. No temporal classification or security-domains field is used. Scarcity does not establish aggression or intent to invade.
- Roles are entity-specific, multi-label portrayals: **Defence readiness**, **Force projection & coercion**, **Target of hostile action**. A portrayal or allegation is not verified attribution.
- Execution adapts Dall’Olio & Vakratsas (2022), Table 5: comparative, endorsement, entertainment/storytelling and mnemonic devices. Apply only to security-related videos. Imagery/visual is omitted by researcher choice for this video-only study. Narrated historical accounts count as storytelling. This advertising-derived adaptation is not a validated persuasion/effectiveness scale.
- Stance applies only to comments, relative to a named claim, policy, action or narrative in the video content. Neutral videos can receive supportive/opposing comments; sentiment and its target are independent. Original comments and saved English translations stay private.
- Public counters are timestamped views, likes and total comments, with nullable missing values, video age and per-1,000-view ratios. Public shares are unavailable. No combined “engagement” sum or causal claims.
- Minimum available comments: **2**. Existing collection retains up to 30 from a pool of up to 100 visible top-level comments. This is not the full audience.

## Workflows

`Sunday research collection` retains the existing discovery/sample design and feeds the conflict taxonomy. `Transcript-based conflict classification` reuses a specified retained batch and refreshes counters for existing eligible videos. It never discovers additional videos or retrieves additional comments. Both share the same single-writer concurrency group and $5 weekly model budget.

The Observatory model policy remains `gpt-5-nano`, switching to `gpt-5.6-luna` at 2026-12-10 00:00 UTC. No expensive fallback is configured. Configuration is in `config/review_models.json`; taxonomy in `config/hybrid.json`; prompts in `prompts/hybrid-framing-1.4.txt`.

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

The public exporter publishes the full sampled source inventory and caption health. AI labels publish immediately as provisional once saved English transcripts support classification; a human review is not a publication prerequisite. Validated human labels override the corresponding AI labels. Only aggregated comment alignment, focus and sentiment are public; raw discussion remains private. Calibration completion is not proof of model reliability.

## Research foundations

- [Dall’Olio & Vakratsas — Advertising creative strategy](https://doi.org/10.1177/00222429221074960): four retained execution categories adapted from the original five.
- [NATO — Countering hybrid threats](https://www.nato.int/en/what-we-do/deterrence-and-defence/countering-hybrid-threats): scope of military and non-military coercion.
- [Hybrid CoE — Hybrid threats](https://www.hybridcoe.fi/hybrid-threats/): attribution and coordinated-activity limits.
- [Mohammad et al. — SemEval 2016 stance detection](https://aclanthology.org/S16-1003/): stance is distinct from sentiment.
- [YouTube video statistics](https://developers.google.com/youtube/v3/docs/videos#statistics): available public counters.

The country frame, random sampling, inclusion probabilities and original collection timestamps are preserved. Caption availability and visibility-based comment sampling limit generalization. No temporal label is collected. Historical actor names and dates stay in source evidence; aggregate portrayals must not be presented as current threat estimates. Raw observations follow the existing 30-day retention policy.

The active execution codebook has four categories. Imagery/visual is retired by researcher choice; historical narration and clear implicit comparisons are explicit adaptations of the source paper. The paper’s execution categories are binary (1 present / 0 absent), not intensity scales; unavailable evidence is not a verified 0. Earlier human reviews remain under their original version, including the superseded groundwater exclusion. Country metadata use title/description, not language alone. `--refresh-engagement` refreshes only existing eligible IDs, preserving original snapshots.

## Calibration update, 5 October 2026

Version 1.3 separates main-message alignment from speaker/presentation praise. Establish the attributed speaker, main proposition, target, and speaker sentiment once per video. Each comment records focus, agreement with that proposition, proposition text, sentiment and its named object. Negative comments can align with a critical speaker. Praise for speaking skill alone is not agreement with policy claims. Neutral reporting of an event is not refuted merely by condemning the event. These are research annotations, not diagnoses or factual verification.

All retained comments undergo independent language verification and English translation, including previously confident English detections. Originals remain immutable and both languages appear together. The form preserves corrections on repeated Disagree clicks, saves select changes, and names incomplete/incompatible fields beside confirmation. Earlier reviews remain attached as calibration evidence, never silently recoded as new human decisions.

National laws and trade agreements are in scope, including European trade with non-European partners. Entertainment requires humor OR drama OR constructed plot; these are alternatives. An identified official presenting a substantive argument can be a knowledgeable-source execution device without certifying expertise or truth. Routine political criticism is not a hostile security attack.

The YouTube API supplies thumbnail URLs, not a background-music flag. The private form displays retained thumbnails and counts explicit caption music cues, clearly marked as incomplete evidence. No cue does not prove silence. A thumbnail is packaging evidence, not evidence of a full story; music is mnemonic only when identity-linked/distinctive, not simply background accompaniment. Imagery is not an active classification field.

Country/topic frequencies and message alignment measure the retained sample only. Inferring rising political capital would require a defined longitudinal measure, stable sampling, target resolution and validation. This calibration batch cannot establish Europe-wide public opinion, causal influence, or a trend. Changes informed by these reviews are development calibration, not an independent accuracy test.

## Four-category release, 5 October 2026

Version 1.4 retires imagery/visual and explicitly includes factual historical narration as storytelling. `eiim.calibration.project_four_categories` creates hash-linked copies of 1.3 classifications/reviews with only the retired field removed. Original records, reviewer names, timestamps and all other judgments remain unchanged. This is schema migration, not a new human review or an AI reclassification. The private form restores authenticated, hash-validated imported decisions; it does not ask the reviewer to repeat them.

Future AI calls receive at most four retained video examples and six retained comment examples from validated human reviews, excluding the video being classified. Corrections are prioritized. Raw examples stay private and follow the existing retention period. This is in-context calibration, not fine-tuning. Reviewed videos are preserved on retries. Training/calibration examples must never be counted as an independent accuracy evaluation; human judgments can also contain uncertainty or inconsistency.

## Scheduled operation and coverage

GitHub Actions collects the weekly sample on Sundays at 05:17 UTC. The retained-source workflow retries captions and resumes AI classification daily at 08:41 UTC without discovering new videos. Both require `EIIM_ENABLE_LIVE=true`, fail explicitly on missing required credentials and share the existing $5 per-batch model ledger. Completed/partial runs trigger a new Pages snapshot. The daily retry stops on YouTube IP blocking; no cookie or proxy bypass is used. A successful eligible-pool classification is not proof of full sample coverage: the public pipeline reports saved, blocked, unavailable and unverified captions separately.

Researcher corrections are preserved as human overrides. Retained validated examples enter later AI prompts (excluding the video itself); lasting codebook rules from the corrections are in versioned prompts. This is prompt calibration, not automatic model training. Examples expire with raw-data retention; written codebook rules persist. Full-week classification remains conditional on obtaining English source text.

## Live presentation

The public page is named **European Security Monitor**. Two compact side panels rotate public city cameras across ten European countries. The verified camera directory is in [CAMERAS.md](CAMERAS.md), with machine-readable metadata in `apps/dashboard/cameras.json`. Each live build checks YouTube live/embeddable status using the existing API key. Video media are never downloaded, proxied, recorded or stored. Streams play muted when the browser permits autoplay, with manual start, pause, hold and next controls. A failed stream enters a temporary cooldown; the client excludes offline and stale catalogue entries.

The source feed cycles the retained weekly inventory every eight seconds, interleaving countries. It pauses on hover, keyboard focus, a selected video, hidden tabs, and explicit pause. Movement does not indicate newly collected evidence. The camera footage is contextual and is never counted as research evidence. The selected custom address and exact DNS setup are recorded in [DOMAIN-SETUP.md](DOMAIN-SETUP.md).
