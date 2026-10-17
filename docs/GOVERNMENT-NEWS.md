# Daily government communications

`config/government_sources.json` is the reviewed directory of exact official communication sections for the 51 countries in `config/countries.json`. The directory URL identifies the publication section; it is not a general government homepage. Finland uses only [Valtioneuvoston uutiset](https://valtioneuvosto.fi/ajankohtaista/uutiset), whose dated entries are marked `Uutinen`. The separate `Tiedotteet` press-release feed is outside the Finland scope. The researcher-supplied Albania, Armenia, Belarus, and Georgia sections are retained. Albania's [English-language presidency News archive](https://president.al/news/?lang=en) has dated entries, but direct automated requests are denied, so it is not yet an enabled collector. Armenia uses the reachable [Prime Minister's English press releases](https://www.primeminister.am/en/press-release/). France uses [Toute l'actualité](https://www.info.gouv.fr/toute-l-actualite), and Cyprus uses [English news posts](https://www.gov.cy/en/news/?q_topic&q_content_type=post&time_period&sort_by=newest). Both currently return HTTP 403 to the collector.

## Collection and schedule

`.github/workflows/government-news.yml` runs daily at **15:00 Europe/Amsterdam**. The October backfill begins on 2026-10-01. Each enabled source has its own saved end timestamp; a later run starts from that source's checkpoint. Date-only sources revisit both touched dates and deduplicate by official article URL. A failed source does not advance its checkpoint. Manual dispatch accepts `since`, `until`, `countries`, and `classify_only` inputs for bounded pilots and classification batches.

Source URL verification and automated collector readiness are separate. As of 2026-10-17, 39 country collectors are enabled. Albania, Cyprus, Finland, France, Ireland, Latvia, Lithuania, Malta, Norway, Romania, Russia, and Ukraine remain disabled while their full dated archives or article bodies cannot be retrieved reliably from the GitHub runner. Romania's cabinet news section and RSS feed are verified, but the GitHub runner repeatedly times out connecting to gov.ro; its checkpoint is retained for a later retry. They appear on the Government Narratives page as **pending collection**, linked to their recorded official sections; missing items are not presented as zero publications. Belgium now uses the reachable [Dutch-language Foreign Affairs ministry news section](https://diplomatie.belgium.be/nl/nieuws); its 2026-10-01 through 2026-10-16 pilot found three dated communications and retrieved all three article bodies. This covers one federal ministry, not the full cabinet. The enabled-code set is `COLLECTOR_READY_CODES` in `scripts/collect_government_news.py`.

The collector reads only dated communications from the reviewed sections, retrieves their full article text, translates it to English, and applies the same `hybrid-framing-1.6` relevance, topic, actor-role, and viewpoint rules used for creator videos. It does not code video delivery/execution or audience comments for government text. Only `id`, official `url`, `country_code`, and `published_at` are sent to the private Supabase `eiim.government_news_links` table. Article text, full translations, and model labels are not stored there. The public site provides official links, English summaries, labels, rationale, and short plain-English Government Watch lines.

Classification is checkpointed in small runs (at most 30 pending items for an all-country run). The first deterministic 10% calibration tranche is held for researcher corrections before the rest is classified. Those corrections in `data/government_corrections.json` are used as examples for later batches. A deterministic 3% sample of classified items enters the `government-human-review-queue` workflow artifact for the researcher's review. Automated review must not be marked as human review. A correction can contain the fields actually changed, for example:

```json
[
  {
    "id": "item-id-from-review-queue",
    "relevance": "not_related",
    "topics": [],
    "roles": []
  }
]
```

The site displays related government communications in the Government Narratives tab and the moving Government Watch bar. The map offers a government-only source filter and light-blue stars sized by the number of related communications. The separate YouTube and live-camera displays remain part of the Situation Room.

