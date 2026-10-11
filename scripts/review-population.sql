-- Replace __BATCH__ only with a validated YYYY-Www retained batch ID.
-- Public IDs only. Use this small result to compute the deterministic review selection.
with retained as (
  select id from eiim.weekly_batches
  where id='__BATCH__' and created_at>=now()-interval '30 days'
), sampled as (
  select s.video_id
  from eiim.sampled_videos s join retained b on b.id=s.batch_id
  where s.purged_at is null and s.payload->>'selected_for_sample'='true'
), access as (
  select distinct on (r.video_id) r.video_id, r.payload
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id
  where r.purged_at is null
    and r.payload->>'policy_version'='english-access-1.0'
  order by r.video_id, r.payload->>'checked_at' desc
), coded as (
  select distinct on (r.video_id) r.video_id, r.payload
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id
  where r.purged_at is null
    and r.payload->>'hybrid_version'='hybrid-framing-1.4'
    and r.payload ? 'label'
  order by r.video_id, r.payload->>'classified_at' desc
), videos as (
  select c.video_id, c.payload
  from coded c join sampled s using(video_id) join access a using(video_id)
  where a.payload->>'eligible'='true'
), comment_ids as (
  select distinct item->>'comment_id' as comment_id
  from videos v cross join lateral jsonb_array_elements(v.payload->'label'->'comments') item
  where nullif(item->>'comment_id','') is not null
)
select jsonb_build_object(
  'as_of', now(),
  'batch', '__BATCH__',
  'video_ids', coalesce((select jsonb_agg(video_id order by video_id) from videos),'[]'::jsonb),
  'comment_ids', coalesce((select jsonb_agg(comment_id order by comment_id) from comment_ids),'[]'::jsonb)
) as review_population;
