# Human validation and researcher review

Status at initial release: **not performed**. Synthetic tests verify implementation behaviour, not social-scientific validity.

## Codebook

For the revised private review classifier, use [the revised codebook and literature
audit](CLASSIFIER_1_1.md). Candidate labels add evidence quotes, transcript coverage
and explicit abstention while preserving the frozen 1.0 baseline described below.

Use the exact definitions and 0–4 anchors in `prompts/sfi-1.0.txt`. Score the title and description, not inferred video speech. Identify the target group and direction before dimensions. Quotation without endorsement and positive praise do not establish sectarian framing. Label explanatory narratives independently of framing strength. For comment clusters, assess semantic coherence, off-topic status and substantive narrative difference independently.

## Private HTML review

The [English-access policy](LANGUAGE_ACCESS.md) filters the active pool. Non-English videos require retrieved English captions/transcripts, including successful YouTube auto-translation. Comment labels and human cluster review use separate English text while preserving originals. The page identifies original audio language and transcript/translation provenance; language alone is not proof of intended audience.

`python -m eiim.cli review-html --batch 2026-W40 --output private/review/index.html`

This generates a self-contained private HTML packet with embedded YouTube videos, retained title/description, AI labels and rationale, per-field Agree / Disagree controls, corrected values, notes, and an explicit Confirm button. The generator can expose source classifications as soon as they are saved, before all comment analytics finish. It offers the available sampled classifications in country/tier/language round-robin order. Finish all QA strata and the required coverage before publication.

Serve only on loopback for video playback and stable browser storage:

`python -m http.server 8770 --bind 127.0.0.1 --directory private/review`

Open `http://127.0.0.1:8770/`. Enter your reviewer name, inspect each source, choose Agree or Disagree for every label, correct disagreements, then Confirm & next. Defer uncertain cases. Download confirmed reviews before closing or clearing browser data. Restore saved reviews from that JSON when needed. A regenerated packet is detected every 30 seconds without overwriting browser decisions.

Import the downloaded JSON with `python -m eiim.cli review-import PATH`. AI-assisted confirmation is recorded explicitly, along with field decisions and notes; it is not an independent blind reliability study. Every field requires a decision, disagreement requires a changed label, and a queue fingerprint prevents importing against changed source labels. The original AI classifications remain unchanged. Import validation finishes before any records are written.

Private packets and raw review data are ignored by Git and never copied into GitHub Pages. The HTML contains no API credentials and does not write directly to Supabase. Browser saves are local; downloading is the durable transfer step. YouTube's [embedded player requirements](https://developers.google.com/youtube/iframe_api_reference) require referrer identification, so a loopback HTTP page works more reliably than opening a `file:` URL. A direct YouTube link is always provided if embedding is blocked by the uploader.

## Review flow

```bash
python -m eiim.cli review-export --output private/review-queue.json
# Human researcher edits human_label, reviewer, reviewed_at in the private file.
python -m eiim.cli review-import private/review-queue.json
python -m eiim.cli validation-report
```

The export includes source observations for coding. It is private and ignored by git. Review queues live in `eiim.human_validation` and can also be inspected in the Supabase table editor. Review-import writes a new append-only row; it never replaces the model label or queue record. Corrections to human labels create another review record.

For a video, `human_label` must include integer `othering`, `aversion`, `moralization`, plus `narratives` and `targets` lists. For comment clusters use boolean `coherent`, `off_topic`, `different_narrative`. Exclusion audits use boolean `news_relevance`. Optional `adjudicated_label` stays separate. For a video review, a researcher can also provide `approved_excerpts` (at most two excerpts, each at most 240 characters) after removing handles, personal names or other unnecessary identifying details. Only these explicitly approved excerpts enter the public export.

Before first publication: review at least 100 unique videos, across countries, languages, tiers, high/low/borderline framing, narratives and uncertain cases; and at least 20 comment clusters. The automatic gate checks counts plus minimum country/language/tier coverage. Researchers must inspect the additional QA strata in the queue; a count gate is not substantive validation. Two independent coders and adjudication are recommended for a defensible validation study, but no inter-rater reliability is claimed from one coder.

The report includes exact agreement per O/A/M dimension, exact agreement on the all-three ≥2 conjunction, and Jaccard overlap for narratives and target labels. It also reports per-dimension 5×5 score confusion matrices, mean absolute error, nonzero precision/recall, unscored pairs and evidence-basis counts. Undefined precision/recall is null, never perfect performance. Comparisons with different or unspecified evidence are descriptive only. These metrics are not chance-corrected reliability. Low agreement is a result to report and address; never invent performance or silently replace model outputs.

## Emerging narratives

`eiim.emerging_narratives` preserves coherent OTHER clusters, weekly recurrence, candidate flags and review status. Candidate ≠ permanent category. To promote a label, a researcher records a decision, edits `config/narratives.json`, bumps its version and creates a new prompt/model version for subsequent batches. Historical taxonomy assignments remain immutable. Promotion changes future coding, not past snapshots.

## Exclusion audit

Approximately 5% of relevance-rejected candidates are retained for review using a deterministic seeded hash draw. Record false negatives by country, language and channel tier. Pending/failed classifications are not treated as negative relevance. Sampling is never conditioned on SFI, narratives, controversy or amplification.
