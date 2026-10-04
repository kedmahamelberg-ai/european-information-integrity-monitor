-- Run on a migrated test or live database; every synthetic row is rolled back.
begin;
set local statement_timeout = '8s';
do $$
declare
 batch text := 'bulk-smoke-' || gen_random_uuid();
 rows jsonb; changed jsonb; result jsonb; rejected boolean;
begin
 insert into eiim.weekly_batches(id,payload,config_hash) values(batch,'{}','smoke');
 select jsonb_agg(jsonb_build_object('table',case when i%2=0 then 'candidate_videos' else 'channel_snapshots' end,
  'record',jsonb_build_object('id',batch||':'||i,'batch_id',batch,'video_id',i::text,
  'payload',jsonb_build_object('description',repeat('x',2000)),'payload_hash','hash-'||i)))
 into rows from generate_series(1,6000) i;
 result:=public.eiim_write(batch,'discovery_complete',rows);
 assert (result->>'accepted')::integer=6000;
 perform public.eiim_write(batch,'discovery_complete',rows);
 assert (select count(*) from eiim.candidate_videos where batch_id=batch)=3000;
 assert (select completed_stages from eiim.weekly_batches where id=batch)=array['discovery_complete'];
 -- An existing immutable conflict must roll back every table and the stage.
 changed:=jsonb_set(rows,'{0,record,payload_hash}','"different"');
 changed:=jsonb_set(changed,'{1,record,id}',to_jsonb(batch||':extra'));
 rejected:=false;
 begin perform public.eiim_write(batch,'sampling_complete',changed);
 exception when raise_exception then rejected:=true; end;
 assert rejected;
 assert not exists(select 1 from eiim.candidate_videos where id=batch||':extra');
 assert (select status from eiim.weekly_batches where id=batch)='discovery_complete';
 -- Conflicting duplicates in a single request must also be rejected.
 rejected:=false;
 begin perform public.eiim_write(batch,null,jsonb_build_array(rows->0,changed->0));
 exception when raise_exception then rejected:=true; end;
 assert rejected;
 rejected:=false;
 begin perform public.eiim_write(batch,null,'[{"table":"weekly_batches","record":{}}]');
 exception when raise_exception then rejected:=true; end;
 assert rejected;
 assert not has_function_privilege('anon','public.eiim_write(text,text,jsonb)','execute');
 assert not has_function_privilege('authenticated','public.eiim_write(text,text,jsonb)','execute');
end $$;
rollback;
