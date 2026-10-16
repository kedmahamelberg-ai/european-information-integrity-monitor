# Daily government communications

`config/government_sources.json` follows the 51-country scope in `config/countries.json`. It lists a central national-government or head-of-government site for each country. The collector checks each site's own RSS/Atom declarations and newsroom links; `official_home` and source reachability are recorded per run. Feed endpoints can change, so the published source directory must be checked against the recorded discoveries.

The scheduled GitHub Actions workflow runs at 08:00 in `Europe/Amsterdam`. Its first run starts at 2026-10-01; later runs start at the end timestamp saved by the previous successful run. A manual dispatch can override `since` for a backfill.

The collector uses RSS/Atom first and then a conservative same-domain newsroom crawl. It deduplicates by source URL, fetches public article text, translates it to English, then classifies the translation against `config/narratives.json`. Communication mode and audience comments are not coded. Only related items appear in the moving government ticker. Gold stars show countries with classified government communications and can be toggled on the map.

The initial calibration tranche classifies a deterministic 10% of discovered items and places them in the downloadable `government-human-review-queue` workflow artifact. The remaining items wait. When the correction array in `data/government_corrections.json` covers every calibration item, the next run classifies the waiting items and includes the reviewed labels as examples. Thereafter, a deterministic 3% sample is included in each run's review artifact. Each correction has the shape:

```json
[
  {
    "id": "item-id-from-review-queue",
    "related": true,
    "primary_narrative": "national_sovereignty",
    "secondary_narratives": ["security_terrorism"]
  }
]
```

To enable scheduled operation, merge this workflow to the repository default branch and ensure `OPENAI_API_KEY` is available as a repository or environment secret. GitHub Pages must already be configured as the repository's deployment target. The workflow refuses to advance the saved collection cursor if fewer than 40 country sites are reachable, preserving the prior cursor for retry.

Public data contain the original source URL, title, short English summary, narrative labels, and rationale. Full article text and full machine translation are used for classification but are not committed or published.
