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
  order by r.video_id, r.payload->>'checked_at' desc, r.created_at desc, r.id desc
), coded as (
  select distinct on (r.video_id) r.video_id, r.payload
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id
  where r.purged_at is null
    and r.payload->>'hybrid_version' in ('hybrid-framing-1.4','hybrid-framing-1.5','hybrid-framing-1.6')
    and r.payload ? 'label'
  order by r.video_id, r.payload->>'classified_at' desc, r.created_at desc, r.id desc
), videos as (
  select c.video_id, c.payload
  from coded c join sampled s using(video_id) join access a using(video_id)
  where a.payload->>'eligible'='true'
), video_comments as (
  select v.video_id,
         coalesce(
           jsonb_agg(distinct item->>'comment_id' order by item->>'comment_id')
             filter (where nullif(item->>'comment_id','') is not null),
           '[]'::jsonb
         ) comment_ids
  from videos v
  left join lateral jsonb_array_elements(
    coalesce(v.payload->'label'->'comments','[]'::jsonb)
  ) item on true
  group by v.video_id
)
select jsonb_build_object(
  'as_of', now(),
  'batch', '__BATCH__',
  'video_ids', coalesce((select jsonb_agg(video_id order by video_id) from videos),'[]'::jsonb),
  'video_comments', coalesce(
    (select jsonb_object_agg(video_id,comment_ids order by video_id) from video_comments),
    '{}'::jsonb
  )
) as review_population;
