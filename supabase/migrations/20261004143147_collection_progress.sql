-- Aggregate operational counts only. No source text, identifiers or model scores.
create function public.eiim_progress()
returns jsonb language sql stable security definer set search_path = '' as $$
 with retained as materialized (
  select batch_id, payload from eiim.candidate_videos where purged_at is null
 ), coverage as (
  select batch_id as batch, coalesce(payload->'countries','[]') countries,
   payload->>'tier' tier, count(*) candidates
  from retained group by 1,2,3
 ), batches as (
  select b.id, b.status, b.payload->>'window_start' window_start,
   b.payload->>'window_end' window_end,
   (select count(*) from retained c where c.batch_id=b.id) candidates,
   (select count(*) from eiim.pipeline_runs r where r.batch_id=b.id and r.purged_at is null and r.payload ? 'relevance_video_id') relevance_checked,
   (select count(*) from eiim.sampled_videos s where s.batch_id=b.id and s.purged_at is null and s.payload->>'selected_for_sample'='true') sampled,
   (select count(*) from eiim.video_classifications v where v.batch_id=b.id and v.purged_at is null) classified,
   (select count(*) from eiim.comments c where c.batch_id=b.id and c.purged_at is null) comments_retained
  from eiim.weekly_batches b where exists(select 1 from retained c where c.batch_id=b.id)
 )
 select jsonb_build_object('as_of',now(),
  'batches',coalesce((select jsonb_agg(to_jsonb(b) order by window_start) from batches b),'[]'),
  'coverage',coalesce((select jsonb_agg(to_jsonb(c)) from coverage c),'[]'));
$$;
revoke all on function public.eiim_progress() from public, anon, authenticated;
grant execute on function public.eiim_progress() to service_role;
notify pgrst, 'reload schema';
