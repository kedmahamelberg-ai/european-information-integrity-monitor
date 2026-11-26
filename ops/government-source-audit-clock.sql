-- A private server clock; GitHub owns the actual audit and saved checkpoint.
create schema if not exists monitor_scheduler;
create table if not exists monitor_scheduler.source_audit_dispatches (
  slot timestamptz primary key,
  preflight_request_id bigint,
  dispatch_request_id bigint,
  result text not null default 'preflight',
  updated_at timestamptz not null default now()
);
alter table monitor_scheduler.source_audit_dispatches enable row level security;
revoke all on monitor_scheduler.source_audit_dispatches from public, anon, authenticated;

create or replace function monitor_scheduler.source_audit_decision(payload jsonb, at_time timestamptz)
returns text language plpgsql immutable set search_path='' as $$
declare local_time timestamp := at_time at time zone 'Europe/Amsterdam';
begin
  if jsonb_typeof(payload->'workflow_runs') is distinct from 'array' then
    return 'invalid GitHub preflight';
  end if;
  if (local_time::time >= time '08:15' and local_time::time < time '09:00')
     or (local_time::time >= time '14:15' and local_time::time < time '15:00') then
    return 'regular collection imminent';
  end if;
  if exists (select 1 from jsonb_array_elements(payload->'workflow_runs') r
      where r->>'name' in ('Daily government communications','Government full-source audit','Test and publish monitor')
        and r->>'status' <> 'completed') then
    return 'government pipeline busy';
  end if;
  if exists (select 1 from jsonb_array_elements(payload->'workflow_runs') r
      where r->>'name'='Government full-source audit'
        and (r->>'created_at')::timestamptz > at_time-interval '55 minutes') then
    -- Includes failures: never blindly retry an unchanged model job.
    return 'recent audit exists';
  end if;
  return 'ready';
end $$;
revoke all on function monitor_scheduler.source_audit_decision(jsonb,timestamptz) from public, anon, authenticated;

create or replace function monitor_scheduler.dispatch_source_audit()
returns text language plpgsql set search_path='' as $$
declare current_time_utc timestamptz := clock_timestamp();
  current_slot timestamptz := date_trunc('hour',current_time_utc at time zone 'UTC') at time zone 'UTC';
  current_minute integer := extract(minute from current_time_utc at time zone 'UTC');
  saved monitor_scheduler.source_audit_dispatches%rowtype;
  reply record;
  decision text;
  token text;
  request bigint;
begin
  if current_minute < 35 or current_minute > 39 then return 'outside audit dispatch window'; end if;
  if not pg_try_advisory_xact_lock(7626112635) then return 'audit preflight already running'; end if;
  select * into saved from monitor_scheduler.source_audit_dispatches where slot=current_slot for update;
  if found and saved.dispatch_request_id is not null then
    select status_code,timed_out,error_msg into reply from net._http_response where id=saved.dispatch_request_id;
    if found then
      update monitor_scheduler.source_audit_dispatches set result=case when reply.status_code=204 then 'dispatch accepted' else 'dispatch failed: HTTP '||coalesce(reply.status_code::text,'unknown') end,
        updated_at=current_time_utc where slot=current_slot;
    end if;
    return 'already dispatched; inspect GitHub before any retry';
  end if;
  if saved.result in ('recent audit exists','regular collection imminent','invalid GitHub preflight','preflight failed') then
    return saved.result;
  end if;
  select decrypted_secret into token from vault.decrypted_secrets where name='monitor_github_actions_dispatch';
  if token is null or token='' then raise exception 'Monitor audit dispatcher credential is missing'; end if;
  if saved.preflight_request_id is not null then
    select status_code,timed_out,error_msg,content into reply from net._http_response where id=saved.preflight_request_id;
    if not found then return 'waiting for GitHub preflight'; end if;
    if reply.status_code is distinct from 200 or reply.timed_out or reply.error_msg is not null then
      update monitor_scheduler.source_audit_dispatches set result='preflight failed',updated_at=current_time_utc where slot=current_slot;
      return 'preflight failed; no audit dispatched';
    end if;
    decision := monitor_scheduler.source_audit_decision(reply.content::jsonb,current_time_utc);
    if decision='ready' then
      select net.http_post(
        url:='https://api.github.com/repos/kedmahamelberg-ai/european-information-integrity-monitor/actions/workflows/government-source-audit.yml/dispatches',
        headers:=jsonb_build_object('Authorization','Bearer '||token,'Accept','application/vnd.github+json','X-GitHub-Api-Version','2022-11-28'),
        body:=jsonb_build_object('ref','main','inputs',jsonb_build_object('limit','15')),
        timeout_milliseconds:=10000) into request;
      update monitor_scheduler.source_audit_dispatches set dispatch_request_id=request,result='dispatch queued',updated_at=current_time_utc where slot=current_slot;
      return 'audit dispatch queued';
    end if;
    update monitor_scheduler.source_audit_dispatches set result=decision,updated_at=current_time_utc where slot=current_slot;
    if decision <> 'government pipeline busy' then return decision; end if;
  end if;
  -- A busy pipeline gets a fresh read on the next minute, never a queued model job.
  select net.http_get(
    url:='https://api.github.com/repos/kedmahamelberg-ai/european-information-integrity-monitor/actions/runs?per_page=100',
    headers:=jsonb_build_object('Authorization','Bearer '||token,'Accept','application/vnd.github+json','X-GitHub-Api-Version','2022-11-28'),
    timeout_milliseconds:=10000) into request;
  insert into monitor_scheduler.source_audit_dispatches(slot,preflight_request_id,result,updated_at)
    values(current_slot,request,'preflight',current_time_utc)
    on conflict(slot) do update set preflight_request_id=excluded.preflight_request_id,result='preflight',updated_at=excluded.updated_at;
  return 'GitHub audit preflight queued';
end $$;
revoke all on function monitor_scheduler.dispatch_source_audit() from public, anon, authenticated;

select cron.schedule('monitor-government-source-audit-hourly','* * * * *',
  'select monitor_scheduler.dispatch_source_audit();');
