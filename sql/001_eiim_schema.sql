-- Research data is isolated; the existing Observatory tables are untouched.
create schema if not exists eiim;
revoke all on schema eiim from public, anon, authenticated;
grant usage on schema eiim to service_role;
create table eiim.weekly_batches (
 id text primary key, payload jsonb not null, status text not null default 'started'
 check(status in ('started','discovery_complete','sampling_complete','comments_complete','classification_complete','analytics_complete','published','failed','pending_budget','awaiting_validation')),
 completed_stages text[] not null default '{}', config_hash text not null,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), frozen_at timestamptz);
alter table eiim.weekly_batches enable row level security;
create table eiim.countries (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 iso2 text generated always as (payload->>'iso2') stored,
 created_at timestamptz not null default now(), purged_at timestamptz);
create index countries_batch on eiim.countries(batch_id);
create index countries_video on eiim.countries(video_id) where video_id is not null;
alter table eiim.countries enable row level security;
create table eiim.geographic_terms (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index geographic_terms_batch on eiim.geographic_terms(batch_id);
create index geographic_terms_video on eiim.geographic_terms(video_id) where video_id is not null;
alter table eiim.geographic_terms enable row level security;
create table eiim.channels (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index channels_batch on eiim.channels(batch_id);
create index channels_video on eiim.channels(video_id) where video_id is not null;
alter table eiim.channels enable row level security;
create table eiim.channel_snapshots (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index channel_snapshots_batch on eiim.channel_snapshots(batch_id);
create index channel_snapshots_video on eiim.channel_snapshots(video_id) where video_id is not null;
alter table eiim.channel_snapshots enable row level security;
create table eiim.search_requests (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index search_requests_batch on eiim.search_requests(batch_id);
create index search_requests_video on eiim.search_requests(video_id) where video_id is not null;
alter table eiim.search_requests enable row level security;
create table eiim.candidate_videos (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 title text generated always as (payload->>'title') stored, published_at text generated always as (payload->>'published_at') stored, channel_id text generated always as (payload->>'channel_id') stored,
 created_at timestamptz not null default now(), purged_at timestamptz);
create index candidate_videos_batch on eiim.candidate_videos(batch_id);
create index candidate_videos_video on eiim.candidate_videos(video_id) where video_id is not null;
alter table eiim.candidate_videos enable row level security;
create table eiim.sampled_videos (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 sampling_probability numeric generated always as ((payload->>'sampling_probability')::numeric) stored check(sampling_probability between 0 and 1), selected_for_sample boolean generated always as ((payload->>'selected_for_sample')::boolean) stored, sampling_stratum text generated always as (payload->>'sampling_stratum') stored,
 created_at timestamptz not null default now(), purged_at timestamptz);
create index sampled_videos_batch on eiim.sampled_videos(batch_id);
create index sampled_videos_video on eiim.sampled_videos(video_id) where video_id is not null;
alter table eiim.sampled_videos enable row level security;
create table eiim.video_country_mentions (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 iso2 text generated always as (payload->>'iso2') stored,
 created_at timestamptz not null default now(), purged_at timestamptz);
create index video_country_mentions_batch on eiim.video_country_mentions(batch_id);
create index video_country_mentions_video on eiim.video_country_mentions(video_id) where video_id is not null;
alter table eiim.video_country_mentions enable row level security;
create table eiim.video_classifications (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 sfi numeric generated always as ((payload->>'sfi')::numeric) stored check(sfi between 0 and 4), classifier_version text generated always as (payload->>'classifier_version') stored,
 created_at timestamptz not null default now(), purged_at timestamptz);
create index video_classifications_batch on eiim.video_classifications(batch_id);
create index video_classifications_video on eiim.video_classifications(video_id) where video_id is not null;
alter table eiim.video_classifications enable row level security;
create table eiim.video_narratives (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index video_narratives_batch on eiim.video_narratives(batch_id);
create index video_narratives_video on eiim.video_narratives(video_id) where video_id is not null;
alter table eiim.video_narratives enable row level security;
create table eiim.video_targets (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index video_targets_batch on eiim.video_targets(batch_id);
create index video_targets_video on eiim.video_targets(video_id) where video_id is not null;
alter table eiim.video_targets enable row level security;
create table eiim.comments (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 comment_id text generated always as (payload->>'comment_id') stored,
 created_at timestamptz not null default now(), purged_at timestamptz);
create index comments_batch on eiim.comments(batch_id);
create index comments_video on eiim.comments(video_id) where video_id is not null;
alter table eiim.comments enable row level security;
create table eiim.comment_embeddings_metadata (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index comment_embeddings_metadata_batch on eiim.comment_embeddings_metadata(batch_id);
create index comment_embeddings_metadata_video on eiim.comment_embeddings_metadata(video_id) where video_id is not null;
alter table eiim.comment_embeddings_metadata enable row level security;
create table eiim.comment_classifications (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index comment_classifications_batch on eiim.comment_classifications(batch_id);
create index comment_classifications_video on eiim.comment_classifications(video_id) where video_id is not null;
alter table eiim.comment_classifications enable row level security;
create table eiim.comment_clusters (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index comment_clusters_batch on eiim.comment_clusters(batch_id);
create index comment_clusters_video on eiim.comment_clusters(video_id) where video_id is not null;
alter table eiim.comment_clusters enable row level security;
create table eiim.narrative_injection_results (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index narrative_injection_results_batch on eiim.narrative_injection_results(batch_id);
create index narrative_injection_results_video on eiim.narrative_injection_results(video_id) where video_id is not null;
alter table eiim.narrative_injection_results enable row level security;
create table eiim.amplification_signals (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 aai numeric generated always as ((payload->>'aai')::numeric) stored check(aai between 0 and 1),
 created_at timestamptz not null default now(), purged_at timestamptz);
create index amplification_signals_batch on eiim.amplification_signals(batch_id);
create index amplification_signals_video on eiim.amplification_signals(video_id) where video_id is not null;
alter table eiim.amplification_signals enable row level security;
create table eiim.cross_video_clusters (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index cross_video_clusters_batch on eiim.cross_video_clusters(batch_id);
create index cross_video_clusters_video on eiim.cross_video_clusters(video_id) where video_id is not null;
alter table eiim.cross_video_clusters enable row level security;
create table eiim.emerging_narratives (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index emerging_narratives_batch on eiim.emerging_narratives(batch_id);
create index emerging_narratives_video on eiim.emerging_narratives(video_id) where video_id is not null;
alter table eiim.emerging_narratives enable row level security;
create table eiim.human_validation (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,
 item_type text generated always as (payload->>'item_type') stored, review_status text generated always as (payload->>'review_status') stored,
 created_at timestamptz not null default now(), purged_at timestamptz);
create index human_validation_batch on eiim.human_validation(batch_id);
create index human_validation_video on eiim.human_validation(video_id) where video_id is not null;
alter table eiim.human_validation enable row level security;
create table eiim.classifier_versions (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index classifier_versions_batch on eiim.classifier_versions(batch_id);
create index classifier_versions_video on eiim.classifier_versions(video_id) where video_id is not null;
alter table eiim.classifier_versions enable row level security;
create table eiim.prompt_versions (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index prompt_versions_batch on eiim.prompt_versions(batch_id);
create index prompt_versions_video on eiim.prompt_versions(video_id) where video_id is not null;
alter table eiim.prompt_versions enable row level security;
create table eiim.taxonomy_versions (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index taxonomy_versions_batch on eiim.taxonomy_versions(batch_id);
create index taxonomy_versions_video on eiim.taxonomy_versions(video_id) where video_id is not null;
alter table eiim.taxonomy_versions enable row level security;
create table eiim.pipeline_runs (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index pipeline_runs_batch on eiim.pipeline_runs(batch_id);
create index pipeline_runs_video on eiim.pipeline_runs(video_id) where video_id is not null;
alter table eiim.pipeline_runs enable row level security;
create table eiim.pipeline_errors (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index pipeline_errors_batch on eiim.pipeline_errors(batch_id);
create index pipeline_errors_video on eiim.pipeline_errors(video_id) where video_id is not null;
alter table eiim.pipeline_errors enable row level security;
create table eiim.cost_events (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index cost_events_batch on eiim.cost_events(batch_id);
create index cost_events_video on eiim.cost_events(video_id) where video_id is not null;
alter table eiim.cost_events enable row level security;
create table eiim.dashboard_snapshots (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index dashboard_snapshots_batch on eiim.dashboard_snapshots(batch_id);
create index dashboard_snapshots_video on eiim.dashboard_snapshots(video_id) where video_id is not null;
alter table eiim.dashboard_snapshots enable row level security;
create table eiim.retention_tombstones (
 id text primary key, batch_id text references eiim.weekly_batches(id), video_id text,
 payload jsonb not null, payload_hash text not null,

 created_at timestamptz not null default now(), purged_at timestamptz);
create index retention_tombstones_batch on eiim.retention_tombstones(batch_id);
create index retention_tombstones_video on eiim.retention_tombstones(video_id) where video_id is not null;
alter table eiim.retention_tombstones enable row level security;

create function public.eiim_batch(p_id text, p_payload jsonb, p_config_hash text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare b eiim.weekly_batches;
begin
 if current_user <> 'postgres' and coalesce(current_setting('request.jwt.claims',true)::jsonb->>'role','') <> 'service_role' then raise exception 'Service role required'; end if;
 insert into eiim.weekly_batches(id,payload,config_hash) values(p_id,p_payload,p_config_hash) on conflict do nothing;
 select * into b from eiim.weekly_batches where id=p_id;
 if b.config_hash<>p_config_hash then raise exception 'Configuration differs from frozen batch; create a correction batch'; end if;
 return to_jsonb(b);
end $$;
create function public.eiim_read(p_table text,p_batch text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare result jsonb;
begin
 if not p_table=any(array['countries','geographic_terms','channels','channel_snapshots','search_requests','candidate_videos','sampled_videos','video_country_mentions','video_classifications','video_narratives','video_targets','comments','comment_embeddings_metadata','comment_classifications','comment_clusters','narrative_injection_results','amplification_signals','cross_video_clusters','emerging_narratives','human_validation','classifier_versions','prompt_versions','taxonomy_versions','pipeline_runs','pipeline_errors','cost_events','dashboard_snapshots','retention_tombstones'] || array['weekly_batches']) then raise exception 'Table not allowed'; end if;
 if p_table='weekly_batches' then
   select coalesce(jsonb_agg(to_jsonb(b)),'[]') into result from eiim.weekly_batches b where p_batch is null or b.id=p_batch;
 else
   execute format('select coalesce(jsonb_agg(jsonb_build_object(''id'',id,''batch_id'',batch_id,''video_id'',video_id,''payload'',payload,''payload_hash'',payload_hash,''purged_at'',purged_at)),''[]'') from eiim.%I where ($1 is null or batch_id=$1)',p_table) into result using p_batch;
 end if;
 return result;
end $$;
create function public.eiim_write(p_batch text,p_stage text,p_rows jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare entry jsonb; rec jsonb; tbl text; existing text; n integer:=0; b eiim.weekly_batches;
begin
 select * into b from eiim.weekly_batches where id=p_batch for update;
 if not found then raise exception 'Unknown batch'; end if;
 if p_stage is not null and not p_stage=any(array['discovery_complete','sampling_complete','comments_complete','classification_complete','analytics_complete','published','failed','pending_budget','awaiting_validation']) then raise exception 'Invalid stage'; end if;
 if jsonb_typeof(p_rows)<>'array' then raise exception 'Rows must be an array'; end if;
 for entry in select value from jsonb_array_elements(p_rows) loop
  tbl:=entry->>'table'; rec:=entry->'record';
  if not tbl=any(array['countries','geographic_terms','channels','channel_snapshots','search_requests','candidate_videos','sampled_videos','video_country_mentions','video_classifications','video_narratives','video_targets','comments','comment_embeddings_metadata','comment_classifications','comment_clusters','narrative_injection_results','amplification_signals','cross_video_clusters','emerging_narratives','human_validation','classifier_versions','prompt_versions','taxonomy_versions','pipeline_runs','pipeline_errors','cost_events','dashboard_snapshots','retention_tombstones']) then raise exception 'Table not allowed'; end if;
  if b.frozen_at is not null and tbl not in ('human_validation','pipeline_runs','pipeline_errors','cost_events','retention_tombstones') then raise exception 'Published snapshot frozen'; end if;
  if rec->>'batch_id' is distinct from p_batch or rec->>'id' is null or rec->>'payload_hash' is null then raise exception 'Invalid record envelope'; end if;
  execute format('select payload_hash from eiim.%I where id=$1',tbl) into existing using rec->>'id';
  if existing is not null and existing<>rec->>'payload_hash' then raise exception 'Immutable record conflict: %',tbl; end if;
  execute format('insert into eiim.%I(id,batch_id,video_id,payload,payload_hash) values($1,$2,$3,$4,$5) on conflict(id) do nothing',tbl) using rec->>'id',p_batch,rec->>'video_id',rec->'payload',rec->>'payload_hash';
  n:=n+1;
 end loop;
 if p_stage is not null then
   update eiim.weekly_batches set status=p_stage,updated_at=now(),
    completed_stages=case when p_stage not in ('failed','pending_budget','awaiting_validation') and not p_stage=any(completed_stages) then array_append(completed_stages,p_stage) else completed_stages end,
    frozen_at=case when p_stage='published' then now() else frozen_at end where id=p_batch;
 end if;
 return jsonb_build_object('accepted',n,'stage',p_stage);
end $$;
create function public.eiim_purge(p_days integer default 30)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare tbl text; n integer; total integer:=0;
begin
 if p_days<1 or p_days>30 then raise exception 'Default retention must be 1–30 days'; end if;
 for tbl in select unnest(array['candidate_videos','comments','channel_snapshots','search_requests','comment_embeddings_metadata','video_classifications','comment_classifications','comment_clusters','cross_video_clusters','dashboard_snapshots','human_validation','emerging_narratives','sampled_videos','pipeline_errors']) loop
   execute format('insert into eiim.retention_tombstones(id,batch_id,payload,payload_hash) select $1||'':''||id,batch_id,jsonb_build_object(''table'',$1,''record_id'',id,''reason'',''retention_expiry'',''purged_at'',now()),payload_hash from eiim.%I where created_at<now()-make_interval(days=>$2) and purged_at is null on conflict do nothing',tbl) using tbl,p_days;
   execute format('update eiim.%I set payload=jsonb_build_object(''retention_deleted'',true),purged_at=now() where created_at<now()-make_interval(days=>$1) and purged_at is null',tbl) using p_days;
   get diagnostics n=row_count; total:=total+n;
 end loop;
 return jsonb_build_object('purged',total);
end $$;
revoke all on function public.eiim_batch(text,jsonb,text) from public, anon, authenticated;
grant execute on function public.eiim_batch(text,jsonb,text) to service_role;
revoke all on function public.eiim_read(text,text) from public, anon, authenticated;
grant execute on function public.eiim_read(text,text) to service_role;
revoke all on function public.eiim_write(text,text,jsonb) from public, anon, authenticated;
grant execute on function public.eiim_write(text,text,jsonb) to service_role;
revoke all on function public.eiim_purge(integer) from public, anon, authenticated;
grant execute on function public.eiim_purge(integer) to service_role;
grant all on all tables in schema eiim to service_role;
