-- Keep private evidence reads below the PostgREST statement timeout.
-- The caller still receives every retained row, but in bounded keyset pages.
create index if not exists pipeline_runs_batch_id_id
  on eiim.pipeline_runs (batch_id, id);

create or replace function public.eiim_read_pipeline_page(
  p_batch text, p_after text default '', p_limit integer default 200
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare result jsonb;
begin
  if p_batch is null or p_batch = '' or p_after is null
      or p_limit is null or p_limit < 1 or p_limit > 200 then
    raise exception 'Invalid private pipeline page request';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', r.id, 'batch_id', r.batch_id, 'video_id', r.video_id,
    'payload', r.payload, 'payload_hash', r.payload_hash,
    'purged_at', r.purged_at
  ) order by r.id), '[]'::jsonb)
  into result
  from (
    select id, batch_id, video_id, payload, payload_hash, purged_at
    from eiim.pipeline_runs
    where batch_id = p_batch and id > p_after
    order by id
    limit p_limit
  ) r;
  return result;
end;
$$;

revoke all on function public.eiim_read_pipeline_page(text,text,integer) from public, anon, authenticated;
grant execute on function public.eiim_read_pipeline_page(text,text,integer) to service_role;
