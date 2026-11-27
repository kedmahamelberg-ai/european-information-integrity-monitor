-- A receipt is unique to one dispatch in one document. It contains no browser identifier.
create table monitor_private.wire_view_receipts (
  receipt uuid primary key,
  item text not null,
  day date not null
);
create index wire_view_receipts_item_day on monitor_private.wire_view_receipts (item, day);
create index wire_view_receipts_expiry on monitor_private.wire_view_receipts (day);
alter table monitor_private.wire_view_receipts enable row level security;
revoke all on monitor_private.wire_view_receipts from public, anon, authenticated;
grant select, insert, delete on monitor_private.wire_view_receipts to service_role;

-- Keep the original browser, reaction, and comment behavior, including for cached clients.
alter function public.field_wire_action(text,uuid,text,text,uuid) set schema monitor_private;
create function public.field_wire_action(item_key text, reader uuid, action text, value text default null, request_id uuid default null)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  result jsonb;
  views bigint;
  today date := (now() at time zone 'Europe/Amsterdam')::date;
begin
  result := monitor_private.field_wire_action(item_key,reader,action,value,request_id);
  if action = 'view' and request_id is not null then
    delete from monitor_private.wire_view_receipts where day < today - 29;
    insert into monitor_private.wire_view_receipts(receipt,item,day)
      values(request_id,item_key,today) on conflict(receipt) do nothing;
  end if;
  select count(*) into views from monitor_private.wire_view_receipts
    where item=item_key and day between today - 29 and today;
  return result || jsonb_build_object('document_views', case when views >= 4 then views end);
end;
$$;
revoke all on function public.field_wire_action(text,uuid,text,text,uuid) from public, anon, authenticated;
grant execute on function public.field_wire_action(text,uuid,text,text,uuid) to service_role;

create function monitor_traffic_private.finding_views(p_path text)
returns bigint language sql stable security definer set search_path = '' as $$
  select sum(total)::bigint from monitor_traffic_private.daily_page_views
  where p_path ~ '^/findings/[a-z0-9]+(-[a-z0-9]+)*/$' and length(p_path) <= 140
    and page_path = p_path and day between (now() at time zone 'Europe/Amsterdam')::date - 29
                                       and (now() at time zone 'Europe/Amsterdam')::date
  having sum(total) >= 4;
$$;
create function public.monitor_finding_views(p_path text)
returns bigint language sql stable security invoker set search_path = '' as $$
  select monitor_traffic_private.finding_views(p_path);
$$;
revoke all on function monitor_traffic_private.finding_views(text), public.monitor_finding_views(text) from public;
grant execute on function monitor_traffic_private.finding_views(text), public.monitor_finding_views(text) to anon,authenticated,service_role;
notify pgrst, 'reload schema';
