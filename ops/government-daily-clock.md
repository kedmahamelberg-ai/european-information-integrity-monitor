# Independent government collection clock

Status: activated October 19, 2026. First daily dispatch October 20 at 15:00 Europe/Amsterdam (13:00 UTC). Vault token expires November 18, 2026; renew before that date. Authenticated read of the workflow endpoint returned HTTP 200.

GitHub scheduled events arrived hours late on October 19. This clock uses Supabase pg_cron to dispatch the existing main-branch workflow at 15:00 Europe/Amsterdam (including daylight-saving changes). GitHub runner queues can still delay actual job start; this removes dependence on GitHub's cron event delivery.

## Activation
1. Create a fine-grained GitHub token with access only to this repository and Actions read/write. No Contents write permission is needed. Set an expiry and a renewal reminder.
2. Store it through Supabase Vault as `monitor_github_actions_dispatch`. Never commit the token or put it in logs.
3. Apply `government-daily-clock.sql` in one transaction in project `jnzibjjejmfochertwco`.
4. Verify the named cron job is active. Inspect cron job history and HTTP response status after 15:00. A queued HTTP request alone does not confirm a successful workflow dispatch.
5. The GitHub cron entries are removed to avoid redundant dispatches. Keep the existing workflow concurrency and checkpoints.

The function sends at most one dispatch per Amsterdam calendar day, in a five-minute window starting at 15:00. It fixes the collection cutoff to 15:00. It supplies no country overrides: the existing 39-country collector allowlist remains authoritative and the 12 pending countries stay disabled.

## Inspection
```sql
select jobname,schedule,active from cron.job
where jobname='monitor-government-1500-amsterdam';

select d.collection_date,d.requested_at,r.status_code,r.timed_out,r.error_msg
from monitor_scheduler.dispatches d
left join net._http_response r on r.id=d.request_id
order by d.collection_date desc limit 7;
```

HTTP response records are transient. If dispatch fails or its outcome is unknown, inspect GitHub runs before any manual retry; never blindly dispatch a second overlapping run. Existing URL deduplication and saved classifications are preserved by the collector. No research data is modified by installation.

To disable, use `cron.alter_job(job_id := <verified job id>, active := false)`. Do not directly update cron.job.
