-- Include source-bearing model response caches in the retention boundary.
create or replace function public.eiim_purge(p_days integer default 30)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare tbl text; n integer; total integer:=0;
begin
 if p_days<1 or p_days>30 then raise exception 'Default retention must be 1–30 days'; end if;
 for tbl in select unnest(array['pipeline_runs','candidate_videos','comments','channel_snapshots','search_requests','comment_embeddings_metadata','video_classifications','comment_classifications','comment_clusters','cross_video_clusters','dashboard_snapshots','human_validation','emerging_narratives','sampled_videos','pipeline_errors']) loop
   execute format('insert into eiim.retention_tombstones(id,batch_id,payload,payload_hash) select $1||'':''||id,batch_id,jsonb_build_object(''table'',$1,''record_id'',id,''reason'',''retention_expiry'',''purged_at'',now()),payload_hash from eiim.%I where created_at<now()-make_interval(days=>$2) and purged_at is null on conflict do nothing',tbl) using tbl,p_days;
   execute format('update eiim.%I set payload=jsonb_build_object(''retention_deleted'',true),purged_at=now() where created_at<now()-make_interval(days=>$1) and purged_at is null',tbl) using p_days;
   get diagnostics n=row_count; total:=total+n;
 end loop;
 return jsonb_build_object('purged',total);
end $$;
