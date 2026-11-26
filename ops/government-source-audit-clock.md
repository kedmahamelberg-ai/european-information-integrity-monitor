# Government source-audit clock

Supabase wakes the main-branch GitHub audit at minute 35 of each hour. The
five-minute dispatch window allows a separate asynchronous GitHub preflight.
The existing collection-completion trigger remains as a backup. Native GitHub
hourly cron is replaced to avoid duplicate wake-ups.

The clock checks the latest 100 runs. It skips an active government collection,
audit or publication, any audit created in the preceding 55 minutes (including a
failed one), and the 45 minutes before the 09:00 and 15:00 Europe/Amsterdam
collections. DST is applied by the database timezone conversion. A busy pipeline
gets a fresh preflight within the window, never a queued overlapping audit.
The existing GitHub `pages` concurrency group also serializes actual execution.

The credential remains in Vault as `monitor_github_actions_dispatch`; no secret
value is returned or written to the repository. Functions use invoker rights in
the private scheduler schema; access is revoked from public API roles and the
small bookkeeping table has RLS enabled. Each slot gets at most one dispatch.
An HTTP 204 means accepted, not completed; verify the GitHub checkpoint and
artifact before calling an audit successful. No unchanged model job is rerun.

Install the checked-in SQL through a reviewed migration. Verify the decision
function with `check-government-source-audit-clock.sql`, the active cron job,
its run history, HTTP outcomes and actual GitHub runs. Do not manually advance
an audit cursor. The GitHub workflow owns the audit state and findings.
