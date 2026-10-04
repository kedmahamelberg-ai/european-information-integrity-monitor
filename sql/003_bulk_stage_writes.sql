-- Avoid per-record query planning for large discovery stages.
create or replace function public.eiim_write(p_batch text,p_stage text,p_rows jsonb)
returns jsonb language plpgsql security definer set search_path = '' set statement_timeout = '45s' as $$
declare tbl text; records jsonb; conflict boolean; n integer:=0; b eiim.weekly_batches;
begin
 select * into b from eiim.weekly_batches where id=p_batch for update;
 if not found then raise exception 'Unknown batch'; end if;
 if p_stage is not null and not p_stage=any(array['discovery_complete','sampling_complete','comments_complete','classification_complete','analytics_complete','published','failed','pending_budget','awaiting_validation']) then raise exception 'Invalid stage'; end if;
 if jsonb_typeof(p_rows) is distinct from 'array' then raise exception 'Rows must be an array'; end if;
 -- Group once, then validate and insert each table as a set. The entire stage
 -- remains atomic under the batch lock, including immutable conflict checks.
 for tbl, records in
  select value->>'table', jsonb_agg(value->'record')
  from jsonb_array_elements(p_rows) group by value->>'table'
 loop
  if tbl is null or not tbl=any(array['countries','geographic_terms','channels','channel_snapshots','search_requests','candidate_videos','sampled_videos','video_country_mentions','video_classifications','video_narratives','video_targets','comments','comment_embeddings_metadata','comment_classifications','comment_clusters','narrative_injection_results','amplification_signals','cross_video_clusters','emerging_narratives','human_validation','classifier_versions','prompt_versions','taxonomy_versions','pipeline_runs','pipeline_errors','cost_events','dashboard_snapshots','retention_tombstones']) then raise exception 'Table not allowed'; end if;
  if b.frozen_at is not null and tbl not in ('human_validation','pipeline_runs','pipeline_errors','cost_events','retention_tombstones') then raise exception 'Published snapshot frozen'; end if;
  if exists (
   select 1 from jsonb_array_elements(records) r
   where jsonb_typeof(r) is distinct from 'object'
    or r->>'batch_id' is distinct from p_batch
    or r->>'id' is null or r->>'payload_hash' is null
  ) then raise exception 'Invalid record envelope'; end if;
  if exists (
   select r->>'id' from jsonb_array_elements(records) r
   group by r->>'id' having count(distinct r->>'payload_hash')>1
  ) then raise exception 'Immutable record conflict: %',tbl; end if;
  execute format(
   'select exists (select 1 from jsonb_to_recordset($1) r(id text,payload_hash text)
    join eiim.%I e on e.id=r.id where e.payload_hash<>r.payload_hash)',tbl)
   into conflict using records;
  if conflict then raise exception 'Immutable record conflict: %',tbl; end if;
  execute format(
   'insert into eiim.%I(id,batch_id,video_id,payload,payload_hash)
    select id,$2,video_id,payload,payload_hash from jsonb_to_recordset($1)
     as r(id text,video_id text,payload jsonb,payload_hash text)
    on conflict(id) do nothing',tbl) using records,p_batch;
  n:=n+jsonb_array_length(records);
 end loop;
 if p_stage is not null then
   update eiim.weekly_batches set status=p_stage,updated_at=now(),
    completed_stages=case when p_stage not in ('failed','pending_budget','awaiting_validation') and not p_stage=any(completed_stages) then array_append(completed_stages,p_stage) else completed_stages end,
    frozen_at=case when p_stage='published' then now() else frozen_at end where id=p_batch;
 end if;
 return jsonb_build_object('accepted',n,'stage',p_stage);
end $$;

notify pgrst, 'reload schema';
