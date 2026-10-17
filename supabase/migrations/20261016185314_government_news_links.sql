-- Persist official source links only. Article text, translations, model labels,
-- and human review evidence are not written to this table.
create table if not exists eiim.government_news_links (
  id text primary key,
  url text not null unique check (url like 'https://%'),
  country_code text not null check (country_code ~ '^[A-Z]{2}$'),
  published_at timestamptz,
  first_seen_at timestamptz not null default now()
);

alter table eiim.government_news_links enable row level security;
revoke all on eiim.government_news_links from public, anon, authenticated;
grant select, insert, update on eiim.government_news_links to service_role;

create or replace function public.upsert_government_news_links(p_links jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_count integer;
begin
  if current_user <> 'postgres' and coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') <> 'service_role' then
    raise exception 'Service role required';
  end if;
  if jsonb_typeof(p_links) <> 'array' then
    raise exception 'Links must be a JSON array';
  end if;
  insert into eiim.government_news_links(id, url, country_code, published_at)
  select id, url, country_code, nullif(published_at, '')::timestamptz
  from jsonb_to_recordset(p_links) as x(id text, url text, country_code text, published_at text)
  where id is not null and url like 'https://%' and country_code ~ '^[A-Z]{2}$'
  on conflict (id) do update
    set url = excluded.url,
        country_code = excluded.country_code,
        published_at = coalesce(excluded.published_at, eiim.government_news_links.published_at);
  get diagnostics v_count = row_count;
  return jsonb_build_object('accepted', v_count);
end;
$$;
revoke all on function public.upsert_government_news_links(jsonb) from public, anon, authenticated;
grant execute on function public.upsert_government_news_links(jsonb) to service_role;
