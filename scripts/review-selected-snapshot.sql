-- Replace __BATCH__ with a validated YYYY-Www retained batch ID.
-- Replace __VIDEO_IDS__ and __COMMENT_IDS__ with SQL-quoted values selected by
-- src/eiim/review_sampling.py. Empty selections use an empty text array.
with params as (
  select array[__VIDEO_IDS__]::text[] selected_videos,
         array[__COMMENT_IDS__]::text[] selected_comments
), retained as (
  select id from eiim.weekly_batches where id='__BATCH__' and created_at>=now()-interval '30 days'
), sampled as (
  select s.video_id
  from eiim.sampled_videos s join retained b on b.id=s.batch_id
  where s.purged_at is null and s.payload->>'selected_for_sample'='true'
), access as (
  select distinct on (r.video_id) r.*
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id
  where r.purged_at is null and r.payload->>'policy_version'='english-access-1.0'
  order by r.video_id, r.payload->>'checked_at' desc
), coded as (
  select distinct on (r.video_id) r.*
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id
  where r.purged_at is null and r.payload->>'hybrid_version'='hybrid-framing-1.4' and r.payload ? 'label'
  order by r.video_id, r.payload->>'classified_at' desc
), population_videos as (
  select c.video_id, c.payload
  from coded c join sampled s using(video_id) join access a using(video_id)
  where a.payload->>'eligible'='true'
), population_comments as (
  select distinct item->>'comment_id' comment_id
  from population_videos v cross join lateral jsonb_array_elements(v.payload->'label'->'comments') item
  where nullif(item->>'comment_id','') is not null
), selected_comment_rows as (
  select c.* from eiim.comments c join retained b on b.id=c.batch_id, params p
  where c.purged_at is null and c.payload->>'comment_id'=any(p.selected_comments)
), context_videos as (
  select unnest(selected_videos) video_id from params
  union
  select video_id from selected_comment_rows
), translation_runs as (
  select distinct on (r.payload->>'comment_translation_id') r.*
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id, params p
  where r.purged_at is null and r.payload->>'comment_translation_id'=any(p.selected_comments)
  order by r.payload->>'comment_translation_id', r.payload->>'translated_at' desc
), selected_runs as (
  select a.* from access a join context_videos v using(video_id)
  union all
  select c.* from coded c join context_videos v using(video_id)
  union all
  select * from translation_runs
), engagement_runs as (
  select distinct on (r.video_id) r.*
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id join context_videos v using(video_id)
  where r.purged_at is null and r.payload ? 'engagement_video_id'
  order by r.video_id, r.payload->>'captured_at' desc
)
select jsonb_build_object(
  'as_of',now(), 'batch','__BATCH__',
  'review_population',jsonb_build_object(
    'batch','__BATCH__',
    'video_ids',coalesce((select jsonb_agg(video_id order by video_id) from population_videos),'[]'::jsonb),
    'comment_ids',coalesce((select jsonb_agg(comment_id order by comment_id) from population_comments),'[]'::jsonb)
  ),
  'tables',jsonb_build_object(
    'weekly_batches',coalesce((select jsonb_agg(to_jsonb(b)) from eiim.weekly_batches b join retained r on r.id=b.id),'[]'::jsonb),
    'sampled_videos',coalesce((select jsonb_agg(to_jsonb(s)) from eiim.sampled_videos s join retained r on r.id=s.batch_id join context_videos v using(video_id) where s.purged_at is null),'[]'::jsonb),
    'candidate_videos',coalesce((select jsonb_agg(to_jsonb(c)) from eiim.candidate_videos c join retained r on r.id=c.batch_id join context_videos v using(video_id) where c.purged_at is null),'[]'::jsonb),
    'pipeline_runs',coalesce((select jsonb_agg(to_jsonb(r)) from (select * from selected_runs union all select * from engagement_runs) r),'[]'::jsonb),
    'comments',coalesce((select jsonb_agg(to_jsonb(c)) from selected_comment_rows c),'[]'::jsonb),
    'human_validation',coalesce((select jsonb_agg(to_jsonb(h)) from eiim.human_validation h join retained r on r.id=h.batch_id join context_videos v using(video_id) where h.purged_at is null),'[]'::jsonb)
  )
) as snapshot;
