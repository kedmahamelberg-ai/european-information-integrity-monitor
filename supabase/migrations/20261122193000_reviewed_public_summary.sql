-- Preserve an aggregate human-reviewed video count with each weekly summary.
-- The previous three-count payload remains accepted during rollout.
create or replace function public.eiim_save_public_summary(
  p_batch text, p_summary jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  previous jsonb;
  field text;
  sampled integer;
  classified integer;
  related integer;
  reviewed integer;
begin
  if p_batch is null or jsonb_typeof(p_summary) <> 'object'
    or (select count(*) from jsonb_object_keys(p_summary)) not in (3, 4)
    or ((select count(*) from jsonb_object_keys(p_summary)) = 4
        and not (p_summary ? 'reviewed_videos')) then
    raise exception 'Invalid public summary';
  end if;
  foreach field in array array[
    'sampled_videos', 'classified_videos', 'security_related_videos'
  ] loop
    if not (p_summary ? field)
      or jsonb_typeof(p_summary -> field) <> 'number'
      or (p_summary ->> field) !~ '^(0|[1-9][0-9]*)$'
      or length(p_summary ->> field) > 7 then
      raise exception 'Invalid public summary count';
    end if;
  end loop;
  if p_summary ? 'reviewed_videos' and (
    jsonb_typeof(p_summary -> 'reviewed_videos') <> 'number'
    or (p_summary ->> 'reviewed_videos') !~ '^(0|[1-9][0-9]*)$'
    or length(p_summary ->> 'reviewed_videos') > 7
  ) then
    raise exception 'Invalid reviewed video count';
  end if;

  select public_summary into previous
  from eiim.weekly_batches where id = p_batch for update;
  if not found then raise exception 'Unknown weekly batch'; end if;
  -- A publication using the earlier three-count format cannot erase a
  -- reviewed count saved by a newer publication.
  if previous ? 'reviewed_videos' and not (p_summary ? 'reviewed_videos') then
    p_summary := p_summary || jsonb_build_object(
      'reviewed_videos', (previous ->> 'reviewed_videos')::integer
    );
  end if;

  sampled := (p_summary ->> 'sampled_videos')::integer;
  classified := (p_summary ->> 'classified_videos')::integer;
  related := (p_summary ->> 'security_related_videos')::integer;
  reviewed := coalesce((p_summary ->> 'reviewed_videos')::integer, 0);
  if related > classified or reviewed > sampled or classified > sampled then
    raise exception 'Public summary counts do not reconcile';
  end if;
  if previous is not null and sampled < (previous ->> 'sampled_videos')::integer then
    raise exception 'Public summary cannot shrink after retention';
  end if;
  if previous ? 'reviewed_videos'
    and reviewed < (previous ->> 'reviewed_videos')::integer then
    raise exception 'Public reviewed count cannot shrink';
  end if;
  update eiim.weekly_batches
    set public_summary = p_summary
    where id = p_batch and public_summary is distinct from p_summary;
  return p_summary;
end;
$$;

revoke all on function public.eiim_save_public_summary(text,jsonb)
  from public, anon, authenticated;
grant execute on function public.eiim_save_public_summary(text,jsonb)
  to service_role;
