-- Run only in the Monitor project, after storing the scoped GitHub token in Vault.
-- No article rows, source settings, or classifications are modified.
create extension if not exists pg_cron;
create extension if not exists pg_net;
create schema if not exists monitor_scheduler;
revoke all on schema monitor_scheduler from public, anon, authenticated;
create table if not exists monitor_scheduler.dispatches (
  collection_date date primary key,
  requested_at timestamptz not null default now(),
  request_id bigint not null
);
alter table monitor_scheduler.dispatches enable row level security;
revoke all on monitor_scheduler.dispatches from public, anon, authenticated;

create or replace function monitor_scheduler.dispatch_daily()
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  local_now timestamp := clock_timestamp() at time zone 'Europe/Amsterdam';
  token text;
  request bigint;
  cutoff timestamptz;
begin
  -- pg_cron checks every minute; this local-time gate handles DST automatically.
  if local_now::time < time '15:00' or local_now::time >= time '15:05' then
    return 'outside dispatch window';
  end if;
  perform pg_advisory_xact_lock(154039);
  if exists (select 1 from monitor_scheduler.dispatches
             where collection_date=local_now::date) then
    return 'already dispatched';
  end if;
  select decrypted_secret into token from vault.decrypted_secrets
    where name='monitor_github_actions_dispatch';
  if token is null or token='' then
    raise exception 'Monitor scheduler credential is missing';
  end if;
  cutoff := (local_now::date + time '15:00') at time zone 'Europe/Amsterdam';
  select net.http_post(
    url := 'https://api.github.com/repos/kedmahamelberg-ai/european-information-integrity-monitor/actions/workflows/government-news.yml/dispatches',
    headers := jsonb_build_object('Authorization','Bearer ' || token,
      'Accept','application/vnd.github+json','X-GitHub-Api-Version','2022-11-28'),
    body := jsonb_build_object('ref','main','inputs',jsonb_build_object(
      'until',to_char(cutoff at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'))),
    timeout_milliseconds := 10000
  ) into request;
  insert into monitor_scheduler.dispatches(collection_date,request_id)
    values(local_now::date,request);
  return 'dispatch queued';
end;
$$;
revoke all on function monitor_scheduler.dispatch_daily() from public, anon, authenticated;

-- Refuse to activate without the credential. Never put the token in this file.
do $$
begin
  if not exists(select 1 from vault.secrets where name='monitor_github_actions_dispatch') then
    raise exception 'Store the repository-scoped Actions token in Vault before activation';
  end if;
end;
$$;
select cron.schedule('monitor-government-1500-amsterdam','* * * * *',
  'select monitor_scheduler.dispatch_daily();');
