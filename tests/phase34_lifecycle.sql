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
values(-92220001,-92220001,'PHASE2-ROLLBACK',current_date-2,1000,0,1000,true);
insert into public.galpon_boxes(id,lote_id,nombre_box,aves_hembra_inicial,aves_macho_inicial) overriding system value
values(-92220001,-92220001,'Original A',900,0),(-92220002,-92220001,'Original B',100,0);
insert into public.registros_diarios(id,lote_id,fecha,dia_vida,consumo_alimento_kg) overriding system value
values(-92220001,-92220001,current_date-2,1,999),(-92220002,-92220001,current_date-1,2,777);
insert into public.registros_diarios_box(id,registro_diario_id,box_id,mortalidad_hembra,mortalidad_macho,descarte_hembra,descarte_macho,consumo_alimento_kg,consumo_agua_litros,peso_promedio_hembra_g,peso_promedio_macho_g) overriding system value
values(-92220001,-92220001,-92220001,0,0,0,0,10,20,1000,0);
insert into public.mediciones_produccion(id,registro_diario_id,box_id,codigo_metrica,valor,created_by) overriding system value
values(-92220001,-92220001,-92220001,'temperatura_ambiente',20,current_setting('avi.phase2_user')::uuid);

\ir ../supabase/migrations/20261121000004_daily_totals_trigger.sql
\ir ../supabase/migrations/20261121000005_lot_closure_and_daily_batch.sql
\ir ../supabase/migrations/20261121000006_weighted_daily_weights.sql
-- Reversible sequence restarts exercise normal RPC identity inserts.
do $$ declare t text; seq regclass; n bigint; begin
 foreach t in array array['registros_diarios','registros_diarios_box','mediciones_produccion'] loop
  select pg_get_serial_sequence('public.'||t,'id')::regclass into seq;
  execute format('select greatest(coalesce(max(id),0)+100000,100000) from public.%I',t) into n;
  execute format('alter sequence %s restart with %s',seq,n);
 end loop;
end $$;
set local role authenticated;
do $$ declare d bigint; payload jsonb; w float8; begin
 payload := '[{"box_id":-92220001,"mortalidad_hembra":9,"mortalidad_macho":0,"descarte_hembra":0,"descarte_macho":0,"consumo_alimento_kg":90,"consumo_agua_litros":180,"peso_promedio_hembra_g":1000,"peso_promedio_macho_g":0,"metricas":[{"codigo_metrica":"temperatura_ambiente","valor":0}]},{"box_id":-92220002,"mortalidad_hembra":1,"mortalidad_macho":0,"descarte_hembra":0,"descarte_macho":0,"consumo_alimento_kg":10,"consumo_agua_litros":20,"peso_promedio_hembra_g":2000,"peso_promedio_macho_g":0,"metricas":[]}]';
 d:=public.save_daily_record(-92220001,current_date-2,payload);
 select peso_promedio_mixto_g into w from public.registros_diarios where id=d;
 if abs(w-1100)>0.001 or w is null then raise exception 'Weighted box mean wrong: %',w; end if;
 if (select consumo_alimento_kg from public.registros_diarios where id=d)<>100 then raise exception 'Feed aggregate wrong'; end if;
 if not exists(select 1 from public.mediciones_produccion where registro_diario_id=d and box_id=-92220001 and valor=0) then raise exception 'Zero metric lost'; end if;
 if public.save_daily_record(-92220001,current_date-2,payload)<>d then raise exception 'Retry duplicated daily record'; end if;
 begin
  perform public.save_daily_record(-92220001,current_date-2,jsonb_set(payload,'{1,metricas}','[{"codigo_metrica":"unknown_metric","valor":1}]'));
  raise exception using errcode='XX000',message='Invalid metric accepted';
 exception when invalid_parameter_value or check_violation then null;
 end;
 if (select consumo_alimento_kg from public.registros_diarios where id=d)<>100 then raise exception 'Failed capture changed feed'; end if;
 begin
  perform public.close_lote(-92220001,current_date-2,'Venta',2000);
  raise exception using errcode='XX000',message='Closure before later daily accepted';
 exception when invalid_parameter_value then null;
 end;
 perform public.close_lote(-92220001,current_date,'Venta',2000);
 perform public.close_lote(-92220001,current_date,'Venta',2000);
 if (select activo from public.lotes where id=-92220001) then raise exception 'Closure not persisted'; end if;
 if not exists(select 1 from public.registros_diarios_box where registro_diario_id=d) then raise exception 'Closure lost history'; end if;
 begin
  perform public.save_daily_record(-92220001,current_date,payload);
  raise exception using errcode='XX000',message='Capture on closed lot accepted';
 exception when invalid_parameter_value then null;
 end;
end $$;
reset role;
select 'Weighted totals, atomic capture, retries, zero metrics, closure and closed capture checks passed' result;
rollback;
