-- Only sampled public identifiers and acquisition status; no raw source text.
select jsonb_build_object(
  'as_of', now(),
  'inventory', coalesce(jsonb_agg(jsonb_build_object(
    'id', s.video_id,
    'batch', s.batch_id,
    'original_language', coalesce(c.payload->>'original_audio_language', 'und'),
    'caption_state', case when exists (
      select 1 from eiim.pipeline_runs r
      where r.batch_id=s.batch_id and r.video_id=s.video_id and r.purged_at is null
        and r.payload->>'policy_version'='english-access-1.0'
        and r.payload->>'eligible'='true'
        and jsonb_array_length(coalesce(r.payload->'transcript_english', '[]'::jsonb))>0
    ) then 'saved' else 'unverified' end
  ) order by s.batch_id desc, s.video_id), '[]'::jsonb)
) as inventory
from eiim.sampled_videos s
join eiim.weekly_batches b on b.id=s.batch_id
join eiim.candidate_videos c on c.batch_id=s.batch_id and c.video_id=s.video_id and c.purged_at is null
where s.purged_at is null and s.payload->>'selected_for_sample'='true'
  and b.created_at >= now()-interval '30 days'
  and 'sampling_complete'=any(b.completed_stages);
