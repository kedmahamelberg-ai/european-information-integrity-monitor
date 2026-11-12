-- Retain only publication counts beyond the 30-day detailed-source window.
alter table eiim.weekly_batches
  add column if not exists public_summary jsonb;

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
begin
  if p_batch is null or jsonb_typeof(p_summary) <> 'object'
    or (select count(*) from jsonb_object_keys(p_summary)) <> 3 then
    raise exception 'Invalid public summary';
  end if;
  foreach field in array array['sampled_videos', 'classified_videos', 'security_related_videos'] loop
    if not (p_summary ? field)
      or jsonb_typeof(p_summary -> field) <> 'number'
      or (p_summary ->> field) !~ '^(0|[1-9][0-9]*)$'
      or length(p_summary ->> field) > 7 then
      raise exception 'Invalid public summary count';
    end if;
  end loop;
  sampled := (p_summary ->> 'sampled_videos')::integer;
  classified := (p_summary ->> 'classified_videos')::integer;
  related := (p_summary ->> 'security_related_videos')::integer;
  if related > classified or classified > sampled then
    raise exception 'Public summary counts do not reconcile';
  end if;
  select public_summary into previous
  from eiim.weekly_batches where id = p_batch for update;
  if not found then raise exception 'Unknown weekly batch'; end if;
  if previous is not null and sampled < (previous ->> 'sampled_videos')::integer then
    raise exception 'Public summary cannot shrink after retention';
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

-- W41 was already purged. Its contribution is the difference between the
-- published W41-W45 snapshot (1835 sampled, 799 classified, 604 related)
-- and the later W42-W45 snapshot (1484 sampled, 660 classified, 506 related).
-- No source identifiers or comment data are reconstructed or retained.
update eiim.weekly_batches
set public_summary = '{"sampled_videos":351,"classified_videos":139,"security_related_videos":98}'::jsonb
where id = '2026-W41' and public_summary is null;
