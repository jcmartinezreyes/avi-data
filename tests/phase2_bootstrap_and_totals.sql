-- psql -X -f tests/phase2_bootstrap_and_totals.sql <connection parameters>
-- Administrator connection, controlled test environment. All writes are rolled back.
\set ON_ERROR_STOP on
begin;
set local statement_timeout = '60s';
\ir ../supabase/migrations/20261121000001_fix_rls_delete_permissions.sql
\ir ../supabase/migrations/20261121000002_fix_create_organization_plan.sql
\ir ../supabase/migrations/20261121000003_protect_boxes_and_add_indexes.sql

select set_config('avi.phase2_user', (select user_id::text from public.organization_memberships where role in ('owner','admin') limit 1), true);
do $$ begin
  if coalesce(current_setting('avi.phase2_user'), '') = '' then
    raise exception 'An existing Auth owner/admin is required';
  end if;
end $$;

savepoint bootstrap;
-- Only this transaction sees the removed memberships; ROLLBACK restores them.
delete from public.organization_memberships where user_id=current_setting('avi.phase2_user')::uuid;
select set_config('request.jwt.claim.sub',current_setting('avi.phase2_user'),true);
set local role authenticated;
select set_config('avi.phase2_org',public.create_organization('  Phase 2 rollback bootstrap  ')::text,true);
do $$ declare n int; begin
  select count(*) into n from public.organizations where id=current_setting('avi.phase2_org')::uuid and name='Phase 2 rollback bootstrap';
  if n<>1 then raise exception 'Organization missing or not trimmed'; end if;
  select count(*) into n from public.organization_memberships where organization_id=current_setting('avi.phase2_org')::uuid and role='owner' and user_id=auth.uid();
  if n<>1 then raise exception 'Owner membership missing'; end if;
  select count(*) into n from public.organization_subscriptions where organization_id=current_setting('avi.phase2_org')::uuid and plan_code='basic' and status='active';
  if n<>1 then raise exception 'Default basic plan missing'; end if;
  begin
    perform public.create_organization('duplicate bootstrap');
    raise exception using errcode='XX000',message='Second bootstrap unexpectedly succeeded';
  exception when raise_exception then null;
  end;
  begin
    update public.organization_subscriptions set plan_code='full' where organization_id=current_setting('avi.phase2_org')::uuid;
    if found then raise exception using errcode='XX000',message='Self-upgrade unexpectedly succeeded'; end if;
  exception when insufficient_privilege then null;
  end;
end $$;
insert into public.granjas(id,nombre,organization_id) overriding system value
values(-92220001,'Phase 2 quota farm',current_setting('avi.phase2_org')::uuid);
insert into public.galpones(id,nombre,granja_id,capacidad) overriding system value
select -92220100-n,'Quota house '||n,-92220001,100 from generate_series(1,10)n;
do $$ begin
  begin
    insert into public.galpones(id,nombre,granja_id,capacidad) overriding system value
    values(-92220200,'House eleven',-92220001,100);
    raise exception using errcode='XX000',message='Basic quota exceeded';
  exception when raise_exception then null;
  end;
end $$;
reset role;
rollback to savepoint bootstrap;

-- Bootstrap failure must leave no partial organization behind.
savepoint unavailable_plan;
delete from public.organization_memberships where user_id=current_setting('avi.phase2_user')::uuid;
update public.subscription_plans set active=false where code='basic';
select set_config('request.jwt.claim.sub',current_setting('avi.phase2_user'),true);
set local role authenticated;
do $$ begin
  begin
    perform public.create_organization('Phase 2 unavailable plan');
    raise exception using errcode='XX000',message='Unavailable plan accepted';
  exception when raise_exception then null;
  end;
  if exists(select 1 from public.organizations where name='Phase 2 unavailable plan') then
    raise exception 'Failed bootstrap left a partial organization';
  end if;
end $$;
reset role;
rollback to savepoint unavailable_plan;

-- Isolated fixture hierarchy, with stable IDs that never advance identity sequences.
select set_config('request.jwt.claim.sub',current_setting('avi.phase2_user'),true);
select set_config('avi.phase2_org',gen_random_uuid()::text,true);
insert into public.organizations(id,name,created_by)
values(current_setting('avi.phase2_org')::uuid,'Phase 2 rollback fixtures',current_setting('avi.phase2_user')::uuid);
insert into public.organization_memberships(organization_id,user_id,role)
values(current_setting('avi.phase2_org')::uuid,current_setting('avi.phase2_user')::uuid,'owner');
update public.organization_subscriptions set plan_code='full' where organization_id=current_setting('avi.phase2_org')::uuid;
insert into public.granjas(id,nombre,organization_id) overriding system value
values(-92220001,'Phase 2 farm',current_setting('avi.phase2_org')::uuid);
insert into public.galpones(id,nombre,granja_id,capacidad) overriding system value
values(-92220001,'Phase 2 house',-92220001,100);
insert into public.lotes(id,galpon_id,codigo_lote,fecha_encaste,aves_hembra,aves_macho,aves_totales,activo) overriding system value
values(-92220001,-92220001,'PHASE2-ROLLBACK',current_date-2,5,5,10,true);
insert into public.galpon_boxes(id,lote_id,nombre_box,aves_hembra_inicial,aves_macho_inicial) overriding system value
values(-92220001,-92220001,'Original A',3,2),(-92220002,-92220001,'Original B',2,3);
insert into public.registros_diarios(id,lote_id,fecha,dia_vida,consumo_alimento_kg) overriding system value
values(-92220001,-92220001,current_date-2,1,999),(-92220002,-92220001,current_date-1,2,777);
insert into public.registros_diarios_box(id,registro_diario_id,box_id,mortalidad_hembra,mortalidad_macho,descarte_hembra,descarte_macho,consumo_alimento_kg,consumo_agua_litros,peso_promedio_hembra_g,peso_promedio_macho_g) overriding system value
values(-92220001,-92220001,-92220001,1,2,1,1,10,20,100,200);
insert into public.mediciones_produccion(id,registro_diario_id,box_id,codigo_metrica,valor,created_by) overriding system value
values(-92220001,-92220001,-92220001,'temperatura_ambiente',20,current_setting('avi.phase2_user')::uuid);

\ir ../supabase/migrations/20261121000004_daily_totals_trigger.sql

do $$ begin
  if (select consumo_alimento_kg from public.registros_diarios where id=-92220001)<>10 then raise exception 'Backfill failed'; end if;
  if (select consumo_alimento_kg from public.registros_diarios where id=-92220002)<>777 then raise exception 'Legacy header without details overwritten'; end if;
end $$;
set local role authenticated;
insert into public.registros_diarios_box(id,registro_diario_id,box_id,mortalidad_hembra,mortalidad_macho,descarte_hembra,descarte_macho,consumo_alimento_kg,consumo_agua_litros,peso_promedio_hembra_g,peso_promedio_macho_g) overriding system value
values(-92220002,-92220001,-92220002,2,1,0,1,15,30,200,400);
do $$ declare d public.registros_diarios; begin
  select * into strict d from public.registros_diarios where id=-92220001;
  if (d.mortalidad_hembra,d.mortalidad_macho,d.descartes,d.consumo_alimento_kg,d.consumo_agua_litros,d.peso_promedio_hembra_g,d.peso_promedio_macho_g,d.peso_promedio_mixto_g)
     is distinct from (3,3,3,25::float8,50::float8,150::float8,300::float8,225::float8) then
    raise exception 'Incorrect aggregate after INSERT';
  end if;
end $$;
update public.registros_diarios_box set consumo_alimento_kg=17 where id=-92220002;
do $$ begin
  if (select consumo_alimento_kg from public.registros_diarios where id=-92220001)<>27 then raise exception 'UPDATE totals failed'; end if;
end $$;
update public.registros_diarios_box set registro_diario_id=-92220002 where id=-92220002;
do $$ begin
  if (select consumo_alimento_kg from public.registros_diarios where id=-92220001)<>10 or (select consumo_alimento_kg from public.registros_diarios where id=-92220002)<>17 then raise exception 'Transfer did not recompute both parents'; end if;
end $$;
delete from public.registros_diarios_box where id=-92220002;
do $$ begin
  if (select consumo_alimento_kg from public.registros_diarios where id=-92220002)<>0 then raise exception 'Last detail removal left stale totals'; end if;
  begin
    delete from public.galpon_boxes where id=-92220001;
    raise exception using errcode='XX000',message='Historical box deletion succeeded';
  exception when foreign_key_violation then null;
  end;
end $$;
reset role;
-- Rollback-safe sequence restarts let the RPC exercise normal identity INSERTs
-- without consuming production sequence values after the test ends.
reset role;
do $$ declare t text; seq regclass; start_id bigint; begin
  foreach t in array array['lotes','galpon_boxes'] loop
    select pg_get_serial_sequence('public.'||t,'id')::regclass into seq;
    execute format('select greatest(coalesce(max(id),0)+100000,100000) from public.%I',t) into start_id;
    execute format('alter sequence %s restart with %s',seq,start_id);
  end loop;
end $$;
create function private.phase2_test_reject_box_name() returns trigger language plpgsql set search_path='' as $$
begin
  if new.nombre_box='Phase 2 reject second box' then
    raise exception 'Intentional rollback test' using errcode='23514';
  end if;
  return new;
end $$;
revoke all on function private.phase2_test_reject_box_name() from public,anon,authenticated;
create trigger phase2_test_reject_box_name before insert on public.galpon_boxes
for each row execute function private.phase2_test_reject_box_name();
set local role authenticated;
do $$
declare payload jsonb; boxes jsonb; created_id bigint; saved_id bigint; n integer;
begin
  payload:=jsonb_build_object('galpon_id',-92220001,'codigo_lote','PHASE2-EDITED','fecha_encaste',(current_date-2)::text,'tipo_produccion','engorde','linea_genetica','Cobb 500','aves_totales',999);
  boxes:='[{"id":-92220001,"nombre_box":"Original A","aves_hembra_inicial":3,"aves_macho_inicial":2},{"id":-92220002,"nombre_box":"Original B","aves_hembra_inicial":2,"aves_macho_inicial":3}]'::jsonb;
  saved_id:=public.save_lote_with_boxes(payload,boxes,-92220001);
  if saved_id<>-92220001 or (select aves_totales from public.lotes where id=saved_id)<>10 then raise exception 'Lot totals must derive from boxes'; end if;
  if (select count(*) from public.galpon_boxes where lote_id=saved_id and id in (-92220001,-92220002))<>2 then raise exception 'Box IDs changed'; end if;
  if not exists(select 1 from public.mediciones_produccion where id=-92220001 and box_id=-92220001) or not exists(select 1 from public.registros_diarios_box where id=-92220001 and box_id=-92220001) then raise exception 'History lost during edit'; end if;
  begin
    perform public.save_lote_with_boxes(payload||'{"codigo_lote":"MUST-NOT-PERSIST"}',boxes-0,-92220001);
    raise exception using errcode='XX000',message='Historical removal unexpectedly accepted';
  exception when foreign_key_violation then null;
  end;
  if (select codigo_lote from public.lotes where id=-92220001)<>'PHASE2-EDITED' then raise exception 'Failed edit partially changed lot'; end if;
  begin
    perform public.save_lote_with_boxes(payload,jsonb_set(boxes,'{1,id}','-92229999'),-92220001);
    raise exception using errcode='XX000',message='Foreign box accepted';
  exception when invalid_parameter_value then null;
  end;
  -- Removing a box that has no history is permitted.
  perform public.save_lote_with_boxes(payload,boxes-1,-92220001);
  if exists(select 1 from public.galpon_boxes where id=-92220002) then raise exception 'Unused box was not removed'; end if;
  if (select aves_totales from public.lotes where id=-92220001)<>5 then raise exception 'Removed box still counted in population'; end if;

  payload:=payload||'{"codigo_lote":"PHASE2-NEW-RPC"}';
  boxes:='[{"nombre_box":"New A","aves_hembra_inicial":3,"aves_macho_inicial":2},{"nombre_box":"Phase 2 reject second box","aves_hembra_inicial":2,"aves_macho_inicial":3}]'::jsonb;
  begin
    perform public.save_lote_with_boxes(payload,boxes);
    raise exception using errcode='XX000',message='Fault injection did not fail';
  exception when check_violation then null;
  end;
  if exists(select 1 from public.lotes where codigo_lote='PHASE2-NEW-RPC') then raise exception 'Failed creation left a partial lot'; end if;
  if exists(select 1 from public.galpon_boxes where nombre_box='New A') then raise exception 'Failed creation left a partial box'; end if;
  created_id:=public.save_lote_with_boxes(payload,jsonb_set(boxes,'{1,nombre_box}','"New B"'));
  select count(*) into n from public.galpon_boxes where lote_id=created_id;
  if n<>2 or (select aves_totales from public.lotes where id=created_id)<>10 then raise exception 'New lot/boxes incomplete'; end if;
  update public.lotes set activo=false where id=created_id;
  begin
    perform public.save_lote_with_boxes(payload,'[{"nombre_box":"No reactivation","aves_hembra_inicial":5,"aves_macho_inicial":5}]',created_id);
    raise exception using errcode='XX000',message='Closed lot edited';
  exception when invalid_parameter_value then null;
  end;
  if (select activo from public.lotes where id=created_id) then raise exception 'Closed lot reactivated'; end if;
end $$;
reset role;
-- A reader and an unrelated user cannot call the RPC to modify a visible ID.
update public.organization_memberships set role='analyst' where organization_id=current_setting('avi.phase2_org')::uuid and user_id=current_setting('avi.phase2_user')::uuid;
set local role authenticated;
do $$ begin
  begin
    perform public.save_lote_with_boxes(jsonb_build_object('galpon_id',-92220001,'codigo_lote','ANALYST-EDIT','fecha_encaste',current_date::text), '[{"id":-92220001,"nombre_box":"Original A","aves_hembra_inicial":3,"aves_macho_inicial":2}]',-92220001);
    raise exception using errcode='XX000',message='Analyst wrote through RPC';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
update public.organization_memberships set role='operator' where organization_id=current_setting('avi.phase2_org')::uuid and user_id=current_setting('avi.phase2_user')::uuid;
set local role authenticated;
do $$ begin
  perform public.save_lote_with_boxes(jsonb_build_object('galpon_id',-92220001,'codigo_lote','PHASE2-OPERATOR','fecha_encaste',(current_date-2)::text), '[{"id":-92220001,"nombre_box":"Original A","aves_hembra_inicial":3,"aves_macho_inicial":2}]',-92220001);
  update public.registros_diarios_box set consumo_alimento_kg=12 where id=-92220001;
  if (select consumo_alimento_kg from public.registros_diarios where id=-92220001)<>12 then raise exception 'Operator cannot synchronize totals'; end if;
end $$;
reset role;
select set_config('request.jwt.claim.sub',gen_random_uuid()::text,true);
set local role authenticated;
do $$ begin
  begin
    perform public.save_lote_with_boxes(jsonb_build_object('galpon_id',-92220001,'codigo_lote','OUTSIDER-EDIT','fecha_encaste',current_date::text), '[{"id":-92220001,"nombre_box":"Original A","aves_hembra_inicial":3,"aves_macho_inicial":2}]',-92220001);
    raise exception using errcode='XX000',message='Unrelated user wrote through RPC';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
select 'Phase 2 bootstrap, quota, atomic RPC, permissions, history protection and totals checks passed' result;
rollback;
