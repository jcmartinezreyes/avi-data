-- Run after migration in a disposable transaction. The deployment dry-run appends
-- an intentional exception so migration history and all fixture writes roll back.
select set_config('avi.ops_user',(select user_id::text from public.organization_memberships where role in ('owner','admin') limit 1),true);
select set_config('request.jwt.claim.sub',current_setting('avi.ops_user'),true);
select set_config('avi.ops_org',gen_random_uuid()::text,true);
select set_config('avi.ops_other',gen_random_uuid()::text,true);
insert into public.organizations(id,name,created_by) values(current_setting('avi.ops_org')::uuid,'AviLab isolated test',current_setting('avi.ops_user')::uuid),(current_setting('avi.ops_other')::uuid,'AviLab inaccessible test',current_setting('avi.ops_user')::uuid);
insert into public.organization_memberships(organization_id,user_id,role) values(current_setting('avi.ops_org')::uuid,current_setting('avi.ops_user')::uuid,'owner');
update public.organization_subscriptions set plan_code='full' where organization_id=current_setting('avi.ops_org')::uuid;
insert into public.granjas(id,nombre,organization_id) overriding system value values(90000000000001,'Synthetic rollback farm',current_setting('avi.ops_org')::uuid);
insert into public.galpones(id,nombre,granja_id,capacidad) overriding system value values(90000000000001,'Synthetic rollback house',90000000000001,1000),(90000000000002,'Synthetic layer house',90000000000001,1000);
insert into public.lotes(id,galpon_id,codigo_lote,fecha_encaste,aves_hembra,aves_macho,aves_totales,activo,tipo_produccion,is_synthetic) overriding system value values(90000000000001,90000000000001,'AVILAB-ROLLBACK-ENGORDE',current_date-2,140,60,200,true,'engorde',true),(90000000000002,90000000000002,'AVILAB-ROLLBACK-LAYER',current_date-2,100,0,100,true,'postura',true);
insert into public.galpon_boxes(id,lote_id,nombre_box,aves_hembra_inicial,aves_macho_inicial) overriding system value values(90000000000001,90000000000001,'A',90,10),(90000000000002,90000000000001,'B',50,50),(90000000000003,90000000000002,'Layer',100,0);
set local role authenticated;
do $$
declare org uuid:=current_setting('avi.ops_org')::uuid;other_org uuid:=current_setting('avi.ops_other')::uuid;
 boxes jsonb;result jsonb;id1 uuid;id2 uuid;id3 uuid;id4 uuid;merged uuid;batch uuid;task_id uuid;incident_id uuid;snapshot_id uuid;count_before int;capture_version int;
 observed text:=to_char((current_date-1)::timestamp,'YYYY-MM-DD')||'T12:00:00-05:00';
begin
 boxes:=jsonb_build_array(jsonb_build_object('box_id',90000000000001,'mortalidad_hembra',0,'mortalidad_macho',0,'descarte_hembra',0,'descarte_macho',0,'consumo_alimento_kg',1,'consumo_agua_litros',2,'peso_promedio_hembra_g',1000,'peso_promedio_macho_g',1000),jsonb_build_object('box_id',90000000000002,'mortalidad_hembra',0,'mortalidad_macho',0,'descarte_hembra',0,'descarte_macho',0,'consumo_alimento_kg',1,'consumo_agua_litros',2,'peso_promedio_hembra_g',2000,'peso_promedio_macho_g',2000));
 -- Partial draft does not create/report facts.
 result:=public.save_daily_capture(90000000000001,current_date-2,jsonb_build_array(jsonb_build_object('box_id',90000000000001,'consumo_alimento_kg',null)),'draft',0);
 if result->>'status'<>'draft' or result->>'daily_id' is not null then raise exception 'Draft emitted production facts';end if;
 result:=public.save_daily_capture(90000000000001,current_date-2,boxes,'submitted',1);
 begin perform public.save_daily_capture(90000000000001,current_date-2,boxes,'submitted',1,'stale');raise exception using errcode='XX000',message='Stale daily write accepted';exception when serialization_failure then null;end;
 begin perform public.save_daily_capture(90000000000001,current_date-2,boxes,'closed',2);raise exception using errcode='XX000',message='Unreviewed period closed';exception when invalid_parameter_value then null;end;
 result:=public.save_daily_capture(90000000000001,current_date-2,boxes,'reviewed',2);
 result:=public.save_daily_capture(90000000000001,current_date-2,boxes,'closed',3);
 begin update public.registros_diarios set consumo_alimento_kg=99 where id=(result->>'daily_id')::bigint;raise exception using errcode='XX000',message='Raw daily API bypassed versioning';exception when insufficient_privilege then null;end;
 result:=public.save_daily_capture(90000000000001,current_date-2,boxes,'reopen',4,'Correct import units');
 if result->>'status'<>'draft' or (select count(*) from public.daily_capture_versions where capture_id=(result->>'id')::uuid)<>5 then raise exception 'Reopening lost audit history';end if;
 result:=public.save_daily_capture(90000000000001,current_date-2,boxes,'submitted',5,'Confirmed original values');
 -- Atomic transfer balances all recorded dates and both sexes, never marks a death.
 id1:=public.record_operation(org,'bird_movement',jsonb_build_object('lote_id',90000000000001,'box_id',90000000000001,'observed_at',observed,'movement','transfer','female',40,'male',0,'destination_box_id',90000000000002),'bird-transfer');
 begin perform public.save_daily_capture(90000000000001,current_date-1,jsonb_set(boxes,'{0,mortalidad_hembra}','60'),'submitted',0);raise exception using errcode='XX000',message='Deaths exceeded post-transfer balance';exception when check_violation or invalid_parameter_value then null;end;
 -- Recipient can lose more than INITIAL count because actual incoming birds exist.
 result:=public.save_daily_capture(90000000000001,current_date-1,jsonb_set(boxes,'{1,mortalidad_hembra}','60'),'submitted',0);
 if abs((select peso_promedio_mixto_g from public.registros_diarios where id=(result->>'daily_id')::bigint)-(220000.0/140))>0.0001 then raise exception 'Header weight ignored actual movement balances';end if;
 -- Measured samples are immutable; replacement removes prior from effective facts.
 id1:=public.record_operation(org,'weighing',jsonb_build_object('lote_id',90000000000001,'observed_at',observed,'sex','hembra','weights_g',jsonb_build_array(1000,1100)),'sample-one');
 id2:=public.record_operation(org,'weighing',jsonb_build_object('lote_id',90000000000001,'observed_at',observed,'sex','hembra','weights_g',jsonb_build_array(1200,1300),'supersedes_id',id1,'quality','corrected','note','Scale calibration'),'sample-correction');
 if exists(select 1 from public.effective_operations_events where id=id1) or not exists(select 1 from public.operations_events where id=id1) then raise exception 'Correction destroyed provenance or doubled current measurement';end if;
 begin update public.operations_events set quantity=999 where id=id2;raise exception using errcode='XX000',message='Immutable event changed';exception when insufficient_privilege then null;end;
 -- Feed inventory and idempotency.
 id1:=public.record_operation(org,'feed_movement',jsonb_build_object('observed_at',observed,'warehouse','Silo A','movement','opening','quantity_kg',100),'feed-opening');
 id2:=public.record_operation(org,'feed_movement',jsonb_build_object('observed_at',observed,'warehouse','Silo A','movement','consumption','quantity_kg',60),'feed-consumption');
 if public.record_operation(org,'feed_movement',jsonb_build_object('observed_at',observed,'warehouse','Silo A','movement','consumption','quantity_kg',60),'feed-consumption')<>id2 then raise exception 'Idempotent retry duplicated feed';end if;
 begin perform public.record_operation(org,'feed_movement',jsonb_build_object('observed_at',observed,'warehouse','Silo A','movement','consumption','quantity_kg',41),'feed-overdraw');raise exception using errcode='XX000',message='Negative silo accepted';exception when check_violation then null;end;
 begin perform public.record_operation(org,'feed_movement',jsonb_build_object('observed_at',observed,'warehouse','Silo A','movement','opening','quantity_kg',50,'supersedes_id',id1,'quality','corrected','note','Incorrect delivery'),'feed-bad-correction');raise exception using errcode='XX000',message='Invalid feed correction accepted';exception when check_violation then null;end;
 -- Egg units preserve many origins and stock through split/merge/classification/hatching.
 id1:=public.record_operation(org,'egg_collection',jsonb_build_object('lote_id',90000000000002,'observed_at',observed,'quantity',100,'round','Morning'),'eggs-round');
 id2:=public.record_operation(org,'egg_split',jsonb_build_object('observed_at',observed,'unit_id',id1,'quantity',40),'eggs-split');
 batch:=public.record_operation(org,'hatch_set',jsonb_build_object('observed_at',observed,'machine','Setter A','inputs',jsonb_build_array(jsonb_build_object('unit_id',id1,'quantity',30),jsonb_build_object('unit_id',id2,'quantity',20))),'hatch-set');
 if (select count(*) from public.hatch_inputs where batch_id=batch)<>2 then raise exception 'Incubation lost origins';end if;
 id3:=public.record_operation(org,'hatch_result',jsonb_build_object('observed_at',observed,'batch_id',batch,'hatched',40,'rejected',5,'unhatched',5,'sample_n',10,'fertile_sample',8),'hatch-result');
 if (select fertile_sample::numeric/sample_n from public.hatch_batches where id=batch)<>0.8 then raise exception 'Embryology uses entire batch denominator';end if;
 merged:=public.record_operation(org,'egg_merge',jsonb_build_object('observed_at',observed,'unit_ids',jsonb_build_array(id1,id2)),'egg-merge');
 if (select sum(quantity) from public.egg_movements where unit_id=merged)<>50 then raise exception 'Merge changed egg quantity';end if;
 id3:=public.record_operation(org,'egg_classification',jsonb_build_object('observed_at',observed,'unit_id',merged,'categories',jsonb_build_object('A',45,'B',5)),'grade-one');
 id4:=public.record_operation(org,'egg_classification',jsonb_build_object('observed_at',observed,'unit_id',merged,'categories',jsonb_build_object('A',40,'B',10),'quality','corrected','note','Manual grade review','supersedes_id',id3),'grade-two');
 perform public.record_operation(org,'egg_transfer',jsonb_build_object('observed_at',observed,'unit_id',merged,'quantity',50,'source_stage','collection','destination','classification'),'egg-to-grade');
 perform public.record_operation(org,'egg_transfer',jsonb_build_object('observed_at',observed,'unit_id',merged,'quantity',50,'source_stage','classification','destination','storage'),'egg-to-store');
 perform public.record_operation(org,'egg_transfer',jsonb_build_object('observed_at',observed,'unit_id',merged,'quantity',10,'source_stage','storage','destination','dispatch'),'egg-dispatch');
 if (select sum(quantity) from public.egg_movements where unit_id=merged and stage='storage')<>40 then raise exception 'Egg stage reconciliation failed';end if;
 -- Tasks require evidence and reject concurrent edits; incident rules deduplicate.
 task_id:=public.record_operation(org,'task',jsonb_build_object('lote_id',90000000000001,'observed_at',observed,'title','Sample weighing','due_date',current_date),'task-one');
 begin perform public.record_operation(org,'task_update',jsonb_build_object('observed_at',observed,'task_id',task_id,'status','done','expected_version',1),'task-no-evidence');raise exception using errcode='XX000',message='Task done without evidence';exception when check_violation then null;end;
 perform public.record_operation(org,'task_update',jsonb_build_object('observed_at',observed,'task_id',task_id,'status','done','expected_version',1,'evidence_event_id',(select id from public.effective_operations_events where organization_id=org and kind='weighing' limit 1)),'task-done');
 begin perform public.record_operation(org,'task_update',jsonb_build_object('observed_at',observed,'task_id',task_id,'status','open','expected_version',1),'task-stale');raise exception using errcode='XX000',message='Task stale version accepted';exception when serialization_failure then null;end;
 incident_id:=public.record_operation(org,'incident',jsonb_build_object('observed_at',observed,'title','Measurement absent','rule_version','coverage-v1','explanation','No measurement received'),'incident-one');
 perform public.record_operation(org,'incident_update',jsonb_build_object('observed_at',observed,'incident_id',incident_id,'expected_version',1,'status','acknowledged'),'incident-acknowledge');
 id4:=public.record_operation(org,'incident',jsonb_build_object('observed_at',observed,'title','Sustained observation','rule_version','coverage-v1','explanation','Measurement still missing'),'incident-repeat');
 if (select count(*) from public.operation_incidents where organization_id=org and rule_version='coverage-v1')<>1
 or not exists(select 1 from public.operation_incidents where id=incident_id and status='acknowledged' and version=3 and explanation='Measurement still missing')
 or not exists(select 1 from public.operations_events where id=incident_id and data->>'explanation'='No measurement received')
 or not exists(select 1 from public.operations_events where id=id4 and related_incident_id=incident_id and data->>'explanation'='Measurement still missing') then raise exception 'Sustained incident lost identity, state, version or observation history';end if;
 if public.record_operation(org,'incident',jsonb_build_object('observed_at',observed,'title','Sustained observation','rule_version','coverage-v1','explanation','Measurement still missing'),'incident-repeat')<>id4 or (select version from public.operation_incidents where id=incident_id)<>3 then raise exception 'Repeated idempotent observation changed incident twice';end if;
 -- Batch failure rolls back its earlier valid row.
 select count(*) into count_before from public.operations_events where organization_id=org;
 begin perform public.import_operations(org,jsonb_build_array(jsonb_build_object('kind','environment','key','import-env','data',jsonb_build_object('lote_id',90000000000001,'observed_at',observed,'temperature_c',25)),jsonb_build_object('kind','egg_collection','key','import-invalid','data',jsonb_build_object('lote_id',90000000000001,'observed_at',observed,'quantity',-1,'round','bad'))),'file-one');raise exception using errcode='XX000',message='Invalid import committed';exception when invalid_parameter_value then null;end;
 if (select count(*) from public.operations_events where organization_id=org)<>count_before then raise exception 'Partial import survived failure';end if;
 snapshot_id:=public.record_operation(org,'snapshot',jsonb_build_object('lote_id',90000000000001,'observed_at',observed,'title','Synthetic closure evidence','cutoff',current_date),'snapshot-one');
 if (select content->>'rules_version' from public.cycle_snapshots where id=snapshot_id)<>'avilab-2026-11' then raise exception 'Snapshot lacks rule version';end if;
 -- Org isolation and privileged actions cannot be bypassed by calling the worker.
 if exists(select 1 from public.daily_captures where organization_id=other_org) then raise exception 'RLS org leak';end if;
 begin perform public.record_operation(other_org,'task',jsonb_build_object('observed_at',observed,'title','Forbidden','due_date',current_date),'forbidden');raise exception using errcode='XX000',message='Cross-organization write accepted';exception when insufficient_privilege then null;end;
 begin perform private.record_operation_worker(other_org,'task',jsonb_build_object('observed_at',observed,'title','Forbidden','due_date',current_date),'forbidden-worker');raise exception using errcode='XX000',message='Private worker bypass accepted';exception when insufficient_privilege then null;end;
end $$;
reset role;
-- Role gates are database checks rather than hidden buttons.
update public.organization_memberships set role='operator' where organization_id=current_setting('avi.ops_org')::uuid;
set local role authenticated;
do $$ begin
 begin perform public.save_daily_capture(90000000000001,current_date-2,(select payload from public.daily_captures where lote_id=90000000000001 and fecha=current_date-2),'reviewed',6);raise exception using errcode='XX000',message='Operator approved capture';exception when insufficient_privilege then null;end;
end $$;
reset role;
update public.organization_memberships set role='analyst' where organization_id=current_setting('avi.ops_org')::uuid;
set local role authenticated;
do $$ begin
 begin perform public.record_operation(current_setting('avi.ops_org')::uuid,'task',jsonb_build_object('observed_at',now(),'title','No write','due_date',current_date),'analyst-write');raise exception using errcode='XX000',message='Analyst wrote event';exception when insufficient_privilege then null;end;
end $$;
reset role;
update public.organization_memberships set role='owner' where organization_id=current_setting('avi.ops_org')::uuid;
-- A real inaccessible row, not an empty-org isolation assertion.
insert into public.operations_events(organization_id,kind,observed_at,source,quality,idempotency_key,data,created_by) values(current_setting('avi.ops_other')::uuid,'health',now(),'manual','observed','hidden-fixture','{}',current_setting('avi.ops_user')::uuid);
set local role authenticated;
do $$ declare org uuid:=current_setting('avi.ops_org')::uuid;data jsonb;before_count int;egg uuid;batch uuid;id1 uuid;original_snapshot jsonb;
 observed text:=to_char((current_date-1)::timestamp,'YYYY-MM-DD')||'T12:00:00-05:00';
begin
 if exists(select 1 from public.operations_events where organization_id=current_setting('avi.ops_other')::uuid) then raise exception 'RLS leaked actual inaccessible fixture';end if;
 if has_function_privilege('anon','private.record_operation_worker(uuid,text,jsonb,text)','EXECUTE') or has_function_privilege('anon','public.save_daily_capture(bigint,date,jsonb,text,integer,text,text,text)','EXECUTE') then raise exception 'Anonymous can invoke commands';end if;
 -- Prearrival checklist is a fact, not automatic clearance or invented arrival.
 perform public.record_operation(org,'readiness',jsonb_build_object('lote_id',90000000000001,'observed_at',(current_date-3)::timestamp at time zone 'America/Bogota','item','House cleaning checked','completed',false),'before-arrival');
 begin perform public.record_operation(org,'egg_classification',jsonb_build_object('observed_at',observed,'categories',jsonb_build_object('A',10)),'orphan-grade');raise exception using errcode='XX000',message='Orphan classification accepted';exception when invalid_parameter_value then null;end;
 egg:=public.record_operation(org,'egg_receipt',jsonb_build_object('observed_at',observed,'quantity',50,'origin_ref','EXT_SYNTHETIC_001'),'external-eggs');
 if (select lote_id from public.egg_units where id=egg) is not null then raise exception 'External egg receipt invented flock';end if;
 begin perform public.record_operation(org,'egg_classification',jsonb_build_object('observed_at',(current_date-2)::timestamp at time zone 'America/Bogota','unit_id',egg,'categories',jsonb_build_object('A',50)),'grade-before-receipt');raise exception using errcode='XX000',message='Classification preceded receipt';exception when invalid_parameter_value then null;end;
 batch:=public.record_operation(org,'hatch_set',jsonb_build_object('observed_at',observed,'machine','Setter B','inputs',jsonb_build_array(jsonb_build_object('unit_id',egg,'quantity',50))),'external-hatch');
 begin perform public.record_operation(org,'hatch_transfer',jsonb_build_object('observed_at',(current_date-2)::timestamp at time zone 'America/Bogota','batch_id',batch,'machine','Hatcher B'),'transfer-before-set');raise exception using errcode='XX000',message='Hatch transfer preceded set';exception when invalid_parameter_value then null;end;
 begin perform public.record_operation(org,'hatch_result',jsonb_build_object('observed_at',observed,'batch_id',batch,'hatched',40,'rejected',5,'unhatched',5,'sample_n',null,'fertile_sample',5),'sample-without-N');raise exception using errcode='XX000',message='Fertility without sample denominator';exception when invalid_parameter_value then null;end;
 perform public.record_operation(org,'hatch_result',jsonb_build_object('observed_at',observed,'batch_id',batch,'hatched',40,'rejected',5,'unhatched',5,'sample_n',null,'fertile_sample',null),'hatch-without-invented-sample');
 -- Missing states cannot be relabeled as zero-valued confirmed facts.
 select payload into data from public.daily_captures where lote_id=90000000000001 and fecha=current_date-2;
 data:=jsonb_set(data,'{0,measurement_states}',jsonb_build_object('consumo_alimento_kg','not_measured'));
 begin perform public.save_daily_capture(90000000000001,current_date-2,data,'submitted',6,'Contradictory flag test');raise exception using errcode='XX000',message='Unmeasured numerical fact submitted';exception when invalid_parameter_value then null;end;
 -- Reopening withdraws losses from balances immediately, then resubmission restores them.
 select payload into data from public.daily_captures where lote_id=90000000000001 and fecha=current_date-1;
 perform public.save_daily_capture(90000000000001,current_date-1,data,'reviewed',1);
 perform public.save_daily_capture(90000000000001,current_date-1,data,'closed',2);
 perform public.save_daily_capture(90000000000001,current_date-1,data,'reopen',3,'Audit weighting withdrawal');
 if abs((select peso_promedio_mixto_g from public.registros_diarios where lote_id=90000000000001 and fecha=current_date-1)-1700)>0.0001 then raise exception 'Withdrawn mortality still affects weighted header';end if;
 perform public.save_daily_capture(90000000000001,current_date-1,data,'submitted',4,'Audit values unchanged');
 select content into original_snapshot from public.cycle_snapshots where organization_id=org limit 1;
 if jsonb_array_length(original_snapshot->'daily_records')<>2 or jsonb_array_length(original_snapshot->'boxes')<>2 then raise exception 'Snapshot omitted actual headers or population configuration';end if;
end $$;
reset role;
-- Subscription permissions are independent of admin permissions.
update public.organization_subscriptions set plan_code='basic' where organization_id=current_setting('avi.ops_org')::uuid;
set local role authenticated;
do $$ begin
 begin perform public.record_operation(current_setting('avi.ops_org')::uuid,'egg_receipt',jsonb_build_object('observed_at',now(),'quantity',10,'origin_ref','NO_ENTITLEMENT'),'basic-hatchery');raise exception using errcode='XX000',message='Basic subscription used hatchery';exception when insufficient_privilege then null;end;
end $$;
reset role;
