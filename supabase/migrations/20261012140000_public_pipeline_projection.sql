-- Keep public-site publication reads proportional to retained evidence used by
-- the exporter. Raw model/cache/error envelopes remain private and are not
-- transferred to GitHub Actions.
create or replace function public.eiim_read_pipeline_public(p_batch text default null)
returns jsonb
language sql
security definer
set search_path = ''
stable
as $$
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', id,
        'batch_id', batch_id,
        'video_id', video_id,
        'payload', payload,
        'payload_hash', payload_hash,
        'purged_at', purged_at
      )
      order by created_at, id
    ),
    '[]'::jsonb
  )
  from eiim.pipeline_runs
  where (p_batch is null or batch_id = p_batch)
    and purged_at is null
    and (
      payload ? 'hybrid_version'
      or payload ? 'english_access_video_id'
      or payload ? 'engagement_video_id'
      or payload ? 'comment_translation_id'
      or payload ? 'caption_recovery_report'
    );
$$;

revoke all on function public.eiim_read_pipeline_public(text)
  from public, anon, authenticated;
grant execute on function public.eiim_read_pipeline_public(text) to service_role;
