# European Information Integrity Monitor

An open computational monitoring system for studying sectarian framing, narrative divergence and suspicious amplification in European YouTube news environments.

**Research beta · implementation and synthetic demonstration. No live findings published.**

[Open the monitor](https://kedmahamelberg-ai.github.io/european-information-integrity-monitor/) · [Methodology](https://kedmahamelberg-ai.github.io/european-information-integrity-monitor/#methodology) · [Deployment](docs/DEPLOYMENT.md) · [Validation protocol](docs/VALIDATION.md)

## What it monitors

- **Sectarian Framing Index (SFI):** independent 0–4 Othering, Aversion and Moralization scores; arithmetic mean and the conjunction rule for strong frames.
- **Explanatory narratives:** multi-label taxonomy, OTHER discovery and a researcher-controlled emerging-narrative queue.
- **Narrative divergence/injection:** coherent off-topic visible-comment clusters with a substantively different classified narrative from the source.
- **Suspicious amplification signals:** duplicate similarity, temporal concentration, cross-video recurrence, topic divergence and narrative concentration. Experimental AAI stays separate from SFI.

The project demonstrates computational information forensics, computational social science, NLP/LLM integration and reproducible information-environment assessment. It is not a bot detector, fact checker, attribution engine or cybersecurity/disk-forensics product.

## Method

A weekly, video-centred search frame is constructed **before any framing or amplification outcomes are measured**. Controlled geographic terms in titles/descriptions identify content concerning a broad universe of 51 European/transcontinental geographic entries. Kosovo is included without a sovereignty determination; XK/XKX are user-assigned codes. Search is bounded and is not a census of YouTube.

Candidates pass a news/public-affairs cascade. Channel institutionalization uses observable metadata and empirical tiers, not credibility labels. Uniform random draws within country × tier strata target 40% low, 40% medium and 20% high benchmark channels. Multi-country candidates have one deterministic sampling-country assignment, while every substantive country reference remains accessible. Exact within-frame inclusion probabilities, seeds, full candidate records and exclusion audits are retained.

Collection runs Sundays at **05:17 UTC (06:17 CET / 07:17 CEST)**. The program computes the last completed Sunday 00:00 through Saturday 23:59:59 in Europe/Amsterdam, including DST. It never includes collection-Sunday uploads. Batch identifiers use the ISO week containing the closing Saturday.

The content sample has no comment-count threshold. The nested comment sample initially requires 20 available comments, retrieves up to 100 top-level comments by API relevance, and retains up to 30 ranked by normalized likes plus replies. This is a visibility sample **within the retrieved pool**, not the global top 30 or a representative audience sample.

## Architecture

```text
YouTube discovery → immutable candidate observations
  → institutionalization + relevance → frozen random sample
  → bounded comment pool → local language / embeddings / clusters
  → structured, budgeted classifications → SFI / narratives / injection / AAI
  → QA and emerging-narrative review → validation gate → public export
                      ↕
       dedicated Supabase project, private eiim schema
```

A small Python package owns research logic. The dashboard is dependency-free HTML/CSS/JavaScript with a local Natural Earth map; it makes no third-party analytics, tile, font or tracking requests. GitHub Pages serves public, explicitly generated exports. Raw comments, model responses, review material and secrets never enter the website build or repository.

- `apps/dashboard/`: interactive map, filters, country details, evidence, methodology and explicit synthetic demonstration.
- `src/eiim/core.py`: pure geography, sampling, scoring, clustering and amplification rules.
- `src/eiim/services.py`: bounded YouTube requests, local embeddings, language detection, structured LLM calls and durable cost ledger.
- `src/eiim/pipeline.py`: restartable research stages and analytics.
- `src/eiim/storage.py`: Supabase service-only RPC adapter and test double.
- `src/eiim/research.py`: stratified QA, emerging-narrative review and agreement.
- `src/eiim/cli.py`: collection, review import/export, validation, retention and publication commands.
- `config/`, `prompts/`: versioned measurement and budget settings.
- `sql/`: reviewed, portable database migrations.
- `tests/`: research invariants, complete fixture pipeline, failure recovery and publication gate.

## Dashboard

Open directly to Europe. Choose a completed period, one or more countries, channel tier and measure. Markers size observations and color the selected measure; a separate amber ring identifies high experimental AAI. Select a country for denominators, dimension prevalence, trends and evidence. Every video exposes batch and classifier provenance. Map markers refer to **content about a country**, not that country's people or government.

The default site shows an honest no-data state. “Explore demonstration” activates synthetic cases generated locally; the banner and all evidence details remain explicitly labelled. These cases never enter Supabase or count as validation.

## Data pipeline and cost controls

The production CLI uses Supabase only. External responses are checkpointed, sampling occurs once, and stage writes commit atomically. Idempotent retries accept identical records and reject conflicting payloads. Successful classification responses are cached; records are append-only until their permitted retention expiry. Published batches are frozen. Changed configurations cannot silently resume an old batch.

Before paid calls, the system applies deterministic preprocessing, language detection, multilingual embeddings, deduplication and coherent clustering. Near-duplicate comments propagate a representative label with explicit provenance. Model failures do not become zero scores. Two attempts maximum; output-schema violations stop processing. The durable cost ledger conservatively reserves a maximum per-call cost before each request; budget exhaustion leaves a recoverable pending batch. Network timeouts retain their reservation to prevent hidden overspending.

Default ceiling: **$5/week estimated LLM charges**, configured and disabled until live collection is explicitly enabled. This is an application ceiling, not an account billing guarantee; verify model prices and set provider-side spend controls. YouTube quota ceiling: 9,000 units/week. The dedicated Supabase project was quoted **$0/month** at creation; free-plan storage and usage limits still apply. No paid models were called during implementation.

## Validation

The adapted text SFI is **not** the validated self-report Political Sectarianism Scale. AAI and similarity thresholds are experimental. Before live analytical publication the gate requires at least 100 unique human-reviewed videos, 20 human-reviewed comment clusters, and recorded coverage of at least three countries, two detected languages and all three channel tiers, at the same classifier version. The QA queue additionally draws high/low/borderline framing, uncertainty, OTHER, amplification and injection cases.

Human labels and adjudications are separate immutable records. Agreement reports calculate exact dimension agreement, exact strong-frame agreement, and Jaccard narrative/target agreement. No reliability result has been invented; observed human validation currently remains **0**. Read [the review protocol](docs/VALIDATION.md).

## Limitations and research use

Search ranking, multilingual dictionary gaps, metadata-only source measurement, channel-data missingness, unequal sampling and highly engaged comment selection all limit generalization. The local relevance prototype scores and embedding-derived off-topic scores are uncalibrated indicators, not validated probabilities. The AAI is a transparent heuristic, not a trained or validated detector. Bounded nearest-neighbour search does not find every semantic recurrence. Findings are descriptive and cannot support causal or actor attribution.

Historical preservation is limited by API permissions and retention obligations. Default raw-data expiry is 30 days, with a daily purge and public-export refresh. It removes raw text/vectors/cached responses and records tombstones rather than pretending historical evidence remains available. A longer research archive needs a separately documented API-permitted basis. Do not change retention merely for convenience. Public live exports are deployment artifacts, not version-controlled data commits.

## Reproduce

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/build_site.py
python -m http.server 8768 --directory build
```

The offline test suite needs only Python 3.11+. It runs the complete pipeline against explicitly synthetic API/model adapters without credentials, model downloads or paid calls. For live collection, install `pip install -e '.[live]'`, configure secrets and follow [deployment instructions](docs/DEPLOYMENT.md). The first embedding-model download and CPU inference consume runtime; the cost ledger records local inference time.

## Methodological inputs

See [source review](docs/SOURCE_REVIEW.md) for the supplied papers/notebook and architectural decisions. The supplied World Monitor archive informed only the map-first concept; no AGPL application code was copied. Natural Earth geometry is public domain. Attached manuscripts, the notebook, and their private metadata are not redistributed.

Code: MIT. Research data are subject to source/API terms and are not covered by the code license.
