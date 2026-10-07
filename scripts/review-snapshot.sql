-- Replace __BATCH__ only with a validated YYYY-Www retained batch ID.
-- Private evidence: save the returned object locally, never print or publish it.
with retained as (
 select id from eiim.weekly_batches where id='__BATCH__' and created_at>=now()-interval '30 days'
), runs as (
 select r.* from eiim.pipeline_runs r join retained b on b.id=r.batch_id
 where r.purged_at is null
), selected_runs as (
 (select distinct on (video_id) * from runs
  where payload->>'policy_version'='english-access-1.0' and payload->>'eligible'='true'
  order by video_id, payload->>'checked_at' desc)
 union
 (select distinct on (video_id) * from runs
  where payload->>'hybrid_version'='hybrid-framing-1.4' and payload ? 'label'
  order by video_id, payload->>'classified_at' desc)
 union
 (select distinct on (payload->>'comment_translation_id') * from runs
  where payload ? 'comment_translation_id'
  order by payload->>'comment_translation_id', payload->>'translated_at' desc)
 union
 (select distinct on (video_id) * from runs where payload ? 'engagement_video_id'
  order by video_id, payload->>'captured_at' desc)
)
select jsonb_build_object('as_of',now(),'tables',jsonb_build_object(
 'weekly_batches',coalesce((select jsonb_agg(to_jsonb(b)) from eiim.weekly_batches b join retained r on r.id=b.id),'[]'::jsonb),
 'sampled_videos',coalesce((select jsonb_agg(to_jsonb(s)) from eiim.sampled_videos s join retained r on r.id=s.batch_id where s.purged_at is null),'[]'::jsonb),
 'candidate_videos',coalesce((select jsonb_agg(to_jsonb(c)) from eiim.candidate_videos c join retained r on r.id=c.batch_id where c.purged_at is null and exists(select 1 from eiim.sampled_videos s where s.batch_id=c.batch_id and s.video_id=c.video_id and s.purged_at is null and s.payload->>'selected_for_sample'='true')),'[]'::jsonb),
 'pipeline_runs',coalesce((select jsonb_agg(to_jsonb(r)) from selected_runs r),'[]'::jsonb),
 'comments',coalesce((select jsonb_agg(to_jsonb(c)) from eiim.comments c join retained r on r.id=c.batch_id where c.purged_at is null),'[]'::jsonb),
 'human_validation',coalesce((select jsonb_agg(to_jsonb(h)) from eiim.human_validation h join retained r on r.id=h.batch_id where h.purged_at is null),'[]'::jsonb)
)) as snapshot;
