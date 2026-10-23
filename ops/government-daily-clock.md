# Independent government collection clock

Status: 15:00 clock activated October 19, 2026. The 09:00 clock and retry phase are added by `government-early-retry-clock.sql`. Vault token expires November 18, 2026; renew before that date. Authenticated read of the workflow endpoint returned HTTP 200.

GitHub scheduled events arrived hours late on October 19. Supabase pg_cron dispatches the main-branch workflow at 09:00 and 15:00 Europe/Amsterdam (including daylight-saving changes). GitHub runner queues can still delay actual job start; this removes dependence on GitHub's cron event delivery. The 09:00 pass checks all ready sources. The 15:00 pass uses restored per-source checkpoints to retry only sources without a successful check that day. If the early run or its cache is missing, the afternoon run checks all ready sources.

## Activation
1. Create a fine-grained GitHub token with access only to this repository and Actions read/write. No Contents write permission is needed. Set an expiry and a renewal reminder.
2. Store it through Supabase Vault as `monitor_github_actions_dispatch`. Never commit the token or put it in logs.
3. Apply `government-daily-clock.sql` in one transaction in project `jnzibjjejmfochertwco`.
4. Verify the named cron job is active. Inspect cron job history and HTTP response status after 15:00. A queued HTTP request alone does not confirm a successful workflow dispatch.
5. The GitHub cron entries are removed to avoid redundant dispatches. Keep the existing workflow concurrency and checkpoints.

Each function sends at most one dispatch per Amsterdam calendar day, in a five-minute window starting at its local target time. The early and afternoon dispatches fix collection cutoffs to 09:00 and 15:00 respectively. They supply no country overrides: the collector allowlist remains authoritative. A source successfully checked at 09:00 resumes from that checkpoint the following morning; its new afternoon publications are delayed, not skipped.

## Malta route
Malta's official DOI SharePoint archive provides dated, paginated releases and article text. The collector checks its archive through Cloudflare WARP's local SOCKS proxy on a GitHub runner; the other sources and classifier retain the normal runner route. The workflow first checks that WARP reports connected, that Cloudflare's trace says `warp=on`, and that the Malta API returns JSON through the proxy. A failed VPN setup leaves the other countries' collection running and records Malta's source failure.

The runner registration accepts Cloudflare WARP's terms. Keep repository variable `MALTA_WARP_TERMS_APPROVED` unset until the account owner has approved that acceptance for automated GitHub runners; set it to `true` only then. A connected WARP client on the owner's Mac does not configure the GitHub runner. WARP does not provide a selectable Malta exit country, so the route is an alternate network path, not a Maltese IP. An isolated Malta `workflow_dispatch` pilot should verify access before relying on the daily schedule.

## Inspection
```sql
select jobname,schedule,active from cron.job
where jobname in ('monitor-government-0900-amsterdam','monitor-government-1500-amsterdam');

select d.collection_date,d.requested_at,r.status_code,r.timed_out,r.error_msg
from monitor_scheduler.dispatches d
left join net._http_response r on r.id=d.request_id
order by d.collection_date desc limit 7;

select d.collection_date,d.requested_at,r.status_code,r.timed_out,r.error_msg
from monitor_scheduler.early_dispatches d
left join net._http_response r on r.id=d.request_id
order by d.collection_date desc limit 7;
```

HTTP response records are transient. If dispatch fails or its outcome is unknown, inspect GitHub runs before any manual retry; never blindly dispatch a second overlapping run. The collector's GitHub Actions summary and `government-source-diagnostics.json` artifact show source-level failures, including when the workflow itself succeeds. Compare a failed official URL from an independent network before labeling it blocked or taken down. Existing URL deduplication and saved classifications are preserved by the collector. No research data is modified by installation.

To disable, use `cron.alter_job(job_id := <verified job id>, active := false)`. Do not directly update cron.job.
