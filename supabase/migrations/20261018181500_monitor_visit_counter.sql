-- The first 45 visits are the GA4 session_start events recorded from 4 to
-- 18 October 2026. Subsequent visits receive an atomic, stable sequence number.
create schema if not exists monitor_private;

create table monitor_private.visit_counter (
  id integer primary key check (id = 1),
  visits bigint not null check (visits >= 0)
);
insert into monitor_private.visit_counter (id, visits) values (1, 45);

create table monitor_private.visit_sessions (
  token uuid primary key,
  visitor_number bigint unique,
  recorded_at timestamptz not null default now()
);

alter table monitor_private.visit_counter enable row level security;
alter table monitor_private.visit_sessions enable row level security;
revoke all on schema monitor_private from public, anon, authenticated;
revoke all on all tables in schema monitor_private from public, anon, authenticated;
grant usage on schema monitor_private to service_role;
grant select, update on monitor_private.visit_counter to service_role;
grant select, insert, update on monitor_private.visit_sessions to service_role;

create function public.monitor_register_visit(p_token uuid)
returns bigint
language plpgsql
volatile
security invoker
set search_path = ''
as $$
declare
  new_session boolean;
  assigned_number bigint;
begin
  if p_token is null then
    raise exception 'Visit token is required';
  end if;

  insert into monitor_private.visit_sessions (token) values (p_token)
  on conflict do nothing;
  new_session := found;

  if new_session then
    update monitor_private.visit_counter
    set visits = visits + 1
    where id = 1
    returning visits into assigned_number;

    update monitor_private.visit_sessions
    set visitor_number = assigned_number
    where token = p_token;
  else
    select visitor_number into assigned_number
    from monitor_private.visit_sessions
    where token = p_token;
  end if;

  return assigned_number;
end;
$$;

revoke all on function public.monitor_register_visit(uuid) from public, anon, authenticated;
grant execute on function public.monitor_register_visit(uuid) to service_role;
