# Government source access diagnosis — 25 October 2026

The researcher requested a Georgia URL fix, a retry of Spain, Azerbaijan and North Macedonia, and a new investigation of the 11 pending sources using the supplied links. No pending collector was enabled by this investigation.

## Georgia recovery

The official Georgian foreign ministry archive links an October 22 communication at `https://mfa.gov.ge/news/320426`. The existing parser accepted only six digits followed by a hyphen and a title. PR #116 accepts six-digit paths with or without that title, retains the exact official URL, and rejects queries, traversal and external URLs. Two regression tests and five recovery tests passed locally; workflow validation passed on GitHub.

The [four-country recovery run](https://github.com/kedmahamelberg-ai/european-information-integrity-monitor/actions/runs/40179302304) discovered seven new Georgian links and classified all seven, leaving zero pending classifications. It restored the existing main checkpoint and used the existing URL hashes and known-item checks. Spain timed out in its archive callback, Azerbaijan reset the connection, and North Macedonia timed out. The combined run returned a failure status because three sources remained unavailable, although the Georgian results were checkpointed. Publication is handled from that checkpoint without rediscovery.

## Pending sources

Requests used normal Chrome User-Agent headers, a fresh curl cookie jar for each site, a five-second connection timeout and a twelve-second overall timeout. TLS certificate validation remained enabled. These observations are from the local collection environment; they do not prove reliable access from a GitHub runner or long-term source availability.

| Country | Exact section checked | Listing | Full article / interpretation |
| --- | --- | --- | --- |
| Albania | https://president.al/news/?lang=en | HTTP 403, Cloudflare challenge | No full-article pass established. |
| Cyprus | https://www.gov.cy/en/news/?q_topic&q_content_type=post&time_period&sort_by=newest | HTTP 200, dated official news cards and pagination | The linked October 25 presidential press release returned HTTP 403. Listing access alone is insufficient. |
| Finland | https://valtioneuvosto.fi/en/current-issues/press-releases | HTTP 403, Cloudflare challenge | Chrome also displayed security verification. No full-article pass established. |
| France | https://www.info.gouv.fr/toute-l-actualite | HTTP 403, Cloudflare challenge | No full-article pass established. |
| Ireland | https://www.gov.ie/en/news/ | HTTP 200 with browser headers | The October 24 severe-weather press release returned HTTP 200 with full text, both in Chrome and direct requests. See the isolated header test below. |
| Latvia | https://www.mk.gov.lv/lv/jaunumi | Connection timeout | No HTTP response obtained; cookie handling cannot remedy a connection timeout. |
| Lithuania | https://lrv.lt/en/news/ | HTTP 403, Cloudflare challenge | Chrome also remained on automatic security verification. The previously accessible RSS feed provides summaries, not full communications. |
| Norway | https://www.regjeringen.no/en/whats-new/news-and-press-releases/id2006120/ | HTTP 403, Cloudflare challenge | A previous GitHub RSS pilot also failed. No reliable complete-article pass established. |
| Romania | https://gov.ro/ro/stiri | Connection timeout | No HTTP response obtained. |
| Russia | http://en.kremlin.ru/acts/news | HTTP 200, dated official documents | The linked `/acts/news/81069` returned HTTP 200 and full text. This is presidential executive-document news; the configured source is the separate cabinet archive at `government.ru/news/`. The supplied route needs its own parser and explicit publisher scope. |
| Ukraine | https://www.kmu.gov.ua/timeline?type=posts&category_id=3 | Redirect to `validate.perfdrive.com`, final HTTP 200 | The returned document was titled `Radware Captcha Page`, not government news. An HTTP 200 must not be counted as successful news access. |

## Ireland: headers, not cookie acceptance

Three otherwise identical direct requests to `/en/news/` gave:

| Request | Result |
| --- | --- |
| Current collector User-Agent | HTTP 403 |
| Existing collector `BROWSER_UA`, no cookies | HTTP 200 |
| Same browser User-Agent with the site's cookie jar | HTTP 200 |

The only response cookie observed was a CSRF cookie. Cookie acceptance is not required for the successful read. The official news page contains six latest items and links to a search archive filtered to `Press release` and `Speech`, sorted by first publication. That archive exposes ten pages of ten results. Page ten reached October 15, so it does not alone establish complete October 1–14 coverage. The `publisher` filter is available for partitioning an eventual complete backfill. Ireland has no implemented collection adapter in the current dispatcher; pending status must not be described simply as an inaccessible website.

## Browser access versus scheduled collection

A normal Chrome session can have different headers, cookies, JavaScript execution and network reputation from a GitHub-hosted Python request. The distinctions here are concrete: Ireland refuses the current User-Agent; several sites return an explicit browser-verification challenge; Latvia and Romania do not establish a connection; Cyprus serves its listing but refuses the sampled article; and Ukraine returns a CAPTCHA instead of news. Certificate-error bypassing would not fix those observed HTTP refusals or connection failures.

Ireland and the supplied Russian presidential route are now candidates for proper dated-archive adapters and a small GitHub runner pilot. They have not yet passed a complete daily collection and October 1 backfill, so all 11 pending sources remain disabled. Do not classify archive teasers as full communications or remove a country from the pending list solely because its listing returns HTTP 200.
