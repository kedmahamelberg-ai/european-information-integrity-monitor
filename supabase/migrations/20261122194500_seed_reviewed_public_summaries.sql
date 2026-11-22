-- Backfill only verified aggregate video-review counts for weeks that are
-- still within or near retention. Raw review evidence remains private.
-- W43: 7 distinct reviewed videos; W47: 15 distinct reviewed videos.
update eiim.weekly_batches
set public_summary = public_summary || jsonb_build_object(
  'reviewed_videos', greatest(
    coalesce((public_summary ->> 'reviewed_videos')::integer, 0),
    case id when '2026-W43' then 7 else 15 end
  )
)
where id in ('2026-W43', '2026-W47')
  and public_summary is not null
  and (public_summary ->> 'sampled_videos')::integer >=
    case id when '2026-W43' then 7 else 15 end;
