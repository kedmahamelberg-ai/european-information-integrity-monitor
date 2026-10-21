-- Let daily retention locate due records without scanning every retained payload.
-- The predicate matches eiim_purge's created_at/active-row condition.
create index if not exists pipeline_runs_retention_due on eiim.pipeline_runs(created_at) where purged_at is null;
create index if not exists candidate_videos_retention_due on eiim.candidate_videos(created_at) where purged_at is null;
create index if not exists comments_retention_due on eiim.comments(created_at) where purged_at is null;
create index if not exists channel_snapshots_retention_due on eiim.channel_snapshots(created_at) where purged_at is null;
create index if not exists search_requests_retention_due on eiim.search_requests(created_at) where purged_at is null;
create index if not exists comment_embeddings_metadata_retention_due on eiim.comment_embeddings_metadata(created_at) where purged_at is null;
create index if not exists video_classifications_retention_due on eiim.video_classifications(created_at) where purged_at is null;
create index if not exists comment_classifications_retention_due on eiim.comment_classifications(created_at) where purged_at is null;
create index if not exists comment_clusters_retention_due on eiim.comment_clusters(created_at) where purged_at is null;
create index if not exists cross_video_clusters_retention_due on eiim.cross_video_clusters(created_at) where purged_at is null;
create index if not exists dashboard_snapshots_retention_due on eiim.dashboard_snapshots(created_at) where purged_at is null;
create index if not exists human_validation_retention_due on eiim.human_validation(created_at) where purged_at is null;
create index if not exists emerging_narratives_retention_due on eiim.emerging_narratives(created_at) where purged_at is null;
create index if not exists sampled_videos_retention_due on eiim.sampled_videos(created_at) where purged_at is null;
create index if not exists pipeline_errors_retention_due on eiim.pipeline_errors(created_at) where purged_at is null;

-- PostgREST's service_role inherits authenticator's 8s timeout by default.
-- Keep this maintenance RPC bounded below the REST API's 60s ceiling.
alter function public.eiim_purge(integer) set statement_timeout = '45s';
