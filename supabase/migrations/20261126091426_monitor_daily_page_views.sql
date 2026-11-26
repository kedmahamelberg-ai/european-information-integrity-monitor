create schema if not exists monitor_traffic_private;
revoke all on schema monitor_traffic_private from public;
grant usage on schema monitor_traffic_private to anon, authenticated, service_role;

create table if not exists monitor_traffic_private.daily_page_views (
  day date not null,
  page_path text not null,
  source text not null check (
    source in ('google', 'chatgpt', 'claude', 'internal', 'other_referral', 'direct_or_unknown')
  ),
  total bigint not null default 1 check (total > 0),
  primary key (day, page_path, source)
);

alter table monitor_traffic_private.daily_page_views enable row level security;
revoke all on monitor_traffic_private.daily_page_views from public, anon, authenticated;
grant select on monitor_traffic_private.daily_page_views to service_role;

create or replace function monitor_traffic_private.record_page_view(p_path text, p_source text)
returns void language plpgsql security definer set search_path = '' as $$
declare
  view_day date := (now() at time zone 'Europe/Amsterdam')::date;
begin
  -- Anonymous page-load counts use only bounded public paths and source categories.
  if p_path is null or length(p_path) > 140 or not (
    p_path in ('/', '/field-wire/', '/about.html', '/contact.html', '/research.html', '/privacy.html')
    or p_path ~ '^/field-wire/[0-9]{4}-[0-9]{2}-[0-9]{2}/$'
    or p_path ~ '^/findings/[a-z0-9]+(-[a-z0-9]+)*/$'
  ) or p_source is null or p_source not in (
    'google', 'chatgpt', 'claude', 'internal', 'other_referral', 'direct_or_unknown'
  ) then
    raise exception 'Invalid Monitor page-view category' using errcode = '22023';
  end if;

  delete from monitor_traffic_private.daily_page_views
    where day < (view_day - interval '13 months')::date;
  insert into monitor_traffic_private.daily_page_views as counts (day, page_path, source)
    values (view_day, p_path, p_source)
    on conflict (day, page_path, source) do update set total = counts.total + 1;
end;
$$;

revoke all on function monitor_traffic_private.record_page_view(text, text) from public;
grant execute on function monitor_traffic_private.record_page_view(text, text)
  to anon, authenticated, service_role;

create or replace function public.monitor_record_page_view(p_path text, p_source text)
returns void language sql security invoker set search_path = '' as $$
  select monitor_traffic_private.record_page_view(p_path, p_source);
$$;

revoke all on function public.monitor_record_page_view(text, text) from public;
grant execute on function public.monitor_record_page_view(text, text)
  to anon, authenticated, service_role;

notify pgrst, 'reload schema';
