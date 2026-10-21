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
    and r.payload->>'eligible'='true'
    and coalesce(r.payload->>'transcript_language','en')='en'
    and r.payload->>'transcript_complete' is distinct from 'false'
    and r.payload_hash <> '7f4757c6b7c321d8773c2648205489d7a72abccb4500f7369a2f582fc0d84d65'
    and jsonb_array_length(coalesce(r.payload->'transcript_english','[]'::jsonb))>0
  order by r.video_id, r.payload->>'checked_at' desc, r.created_at desc, r.id desc
), coded as (
  select * from (
    select distinct on (r.video_id) r.*
    from eiim.pipeline_runs r join retained b on b.id=r.batch_id
    where r.purged_at is null and r.payload->>'hybrid_version' in ('hybrid-framing-1.4','hybrid-framing-1.5','hybrid-framing-1.6','hybrid-framing-1.7') and r.payload ? 'label'
    order by r.video_id, r.payload->>'classified_at' desc, r.created_at desc, r.id desc
  ) latest
  where latest.payload->>'transcript_truncated' is distinct from 'true'
    and latest.id <> '2026-W40:hybrid:hybrid-framing-1.4:-vCnvdiXv2s:388d431769301e06d69e'
), population_videos as (
  select c.video_id, c.payload
  from coded c join sampled s using(video_id) join access a using(video_id)
  where a.payload->>'eligible'='true'
), population_video_comments as (
  select v.video_id,
         coalesce(
           jsonb_agg(distinct item->>'comment_id' order by item->>'comment_id')
             filter (where nullif(item->>'comment_id','') is not null),
           '[]'::jsonb
         ) comment_ids
  from population_videos v
  left join lateral jsonb_array_elements(
    coalesce(v.payload->'label'->'comments','[]'::jsonb)
  ) item on true
  group by v.video_id
), selected_comment_rows as (
  select c.* from eiim.comments c join retained b on b.id=c.batch_id, params p
  where c.purged_at is null
    and c.video_id=any(p.selected_videos)
    and c.payload->>'comment_id'=any(p.selected_comments)
), context_videos as (
  select unnest(selected_videos) video_id from params
), translation_runs as (
  select distinct on (r.payload->>'comment_translation_id') r.*
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id, params p
  where r.purged_at is null and r.payload->>'comment_translation_id'=any(p.selected_comments)
  order by r.payload->>'comment_translation_id', r.payload->>'translated_at' desc, r.created_at desc, r.id desc
), reviewed_source_runs as (
  select distinct on (r.id) r.*
  from eiim.pipeline_runs r
  join retained b on b.id=r.batch_id
  join eiim.human_validation h on h.batch_id=r.batch_id
    and h.video_id=r.video_id and h.purged_at is null
    and h.payload->>'queue_record_id'=r.id
  join context_videos v on v.video_id=r.video_id
  where r.purged_at is null
  order by r.id
), selected_runs as (
  select distinct on (id) *
  from (
    select a.* from access a join context_videos v using(video_id)
    union all
    select c.* from coded c join context_videos v using(video_id)
    union all
    select * from translation_runs
    union all
    select * from reviewed_source_runs
  ) sources
  order by id
), engagement_runs as (
  select distinct on (r.video_id) r.*
  from eiim.pipeline_runs r join retained b on b.id=r.batch_id join context_videos v using(video_id)
  where r.purged_at is null and r.payload ? 'engagement_video_id'
  order by r.video_id, r.payload->>'captured_at' desc, r.created_at desc, r.id desc
)
select jsonb_build_object(
  'as_of',now(), 'batch','__BATCH__',
  'review_population',jsonb_build_object(
    'batch','__BATCH__',
    'video_ids',coalesce((select jsonb_agg(video_id order by video_id) from population_videos),'[]'::jsonb),
    'video_comments',coalesce(
      (select jsonb_object_agg(video_id,comment_ids order by video_id) from population_video_comments),
      '{}'::jsonb
    )
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
