create table monitor_private.wire_readers (
  item text not null, token uuid not null, viewed boolean not null default false,
  reaction text check (reaction in ('like','dislike','love','thinking')),
  primary key (item, token)
);
create table monitor_private.wire_comments (
  id uuid primary key, item text not null, token uuid not null,
  body text not null check (length(body) between 1 and 500),
  posted timestamptz not null default now()
);
create index wire_comments_recent on monitor_private.wire_comments(item, posted desc);
create index wire_comments_by_reader on monitor_private.wire_comments(token, posted desc);
alter table monitor_private.wire_readers enable row level security;
alter table monitor_private.wire_comments enable row level security;
revoke all on monitor_private.wire_readers, monitor_private.wire_comments from public, anon, authenticated;
grant select, insert, update on monitor_private.wire_readers to service_role;
grant select, insert on monitor_private.wire_comments to service_role;

create function public.field_wire_action(item_key text, reader uuid, action text, value text default null, request_id uuid default null)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare views integer;
begin
  if reader is null or item_key is null or item_key !~ '^[a-zA-Z0-9_-]{3,80}$' then
    raise exception 'Invalid dispatch';
  end if;
  if action = 'view' then
    insert into monitor_private.wire_readers as r(item,token,viewed) values(item_key,reader,true)
    on conflict (item,token) do update set viewed=true where not r.viewed;
  elsif action = 'react' then
    insert into monitor_private.wire_readers(item,token,reaction) values(item_key,reader,nullif(value,''))
    on conflict(item,token) do update set reaction=excluded.reaction;
  elsif action = 'comment' then
    perform pg_advisory_xact_lock(hashtextextended(reader::text,0));
    perform pg_advisory_xact_lock(hashtextextended(item_key,1));
    if not exists(select from monitor_private.wire_comments where id=request_id and token=reader and item=item_key) then
      if exists(select from monitor_private.wire_comments where token=reader and posted>now()-interval '30 seconds')
        or (select count(*) from monitor_private.wire_comments where item=item_key and posted>now()-interval '1 minute')>=20 then
        raise exception 'Please wait before posting again';
      end if;
      insert into monitor_private.wire_comments(id,item,token,body) values(request_id,item_key,reader,btrim(value));
    end if;
  elsif action <> 'read' or action is null then
    raise exception 'Unknown action';
  end if;
  select count(*) into views from monitor_private.wire_readers where item=item_key and viewed;
  return jsonb_build_object('views',case when views>3 then views end,
    'mine',(select reaction from monitor_private.wire_readers where item=item_key and token=reader),
    'reactions',coalesce((select jsonb_object_agg(reaction,n) from
      (select reaction,count(*) n from monitor_private.wire_readers where item=item_key and reaction is not null group by reaction) t),'{}'),
    'comments',coalesce((select jsonb_agg(body order by posted desc) from
      (select body,posted from monitor_private.wire_comments where item=item_key order by posted desc limit 30) t),'[]'));
end;
$$;
revoke all on function public.field_wire_action(text,uuid,text,text,uuid) from public, anon, authenticated;
grant execute on function public.field_wire_action(text,uuid,text,text,uuid) to service_role;
