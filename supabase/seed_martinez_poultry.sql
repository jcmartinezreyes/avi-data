-- AviData demonstration snapshot v1. Run as database administrator after phases 1–4.
-- This script ADDS 60 namespaced synthetic lots; it does not replace existing lots.
-- Snapshot stays fixed at 2026-11-21 on every execution.
-- Sources: Cobb500 Broiler Performance & Nutrition Supplement (2022), as-hatched,
-- https://www.cobbgenetics.com/assets/Cobb-Files/2022-Cobb500-Broiler-Performance-Nutrition-Supplement.pdf
-- Ross308 Broiler Performance Objectives (2022), as-hatched,
-- https://aa-intl.aviagen.com/assets/Tech_Center/Ross_Broiler/RossxRoss308-BroilerPerformanceObjectives2022-EN.pdf
-- Weekly targets are linearly interpolated. Deterministic Box–Muller normal draws
-- use nominal CV 9%, truncated at +/-2.5 SD for plausible demo ranges.
-- Closed lots have consolidated daily records. Active lots additionally have one
-- mixed-sex box and matching daily detail so future box capture stays consistent.
-- Existing namespaced records must match this seed; manual changes cause an abort.
-- No organizations, memberships or subscriptions are created or altered.

begin;
set local statement_timeout = '120s';

create temp table mp_seed_context on commit drop as
select id as organization_id, date '2026-11-21' as snapshot
from public.organizations where name = 'Martinez_Poultry';

do $$ begin
  if (select count(*) from mp_seed_context) <> 1 then
    raise exception 'Expected exactly one existing Martinez_Poultry organization';
  end if;
  if not exists(select 1 from pg_roles where rolname=current_user and (rolsuper or rolbypassrls)) then
    raise exception 'Run this synthetic import with an administrative database connection';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('avidata:seed:martinez_poultry:v1:' || organization_id::text,0))
  from mp_seed_context;
  if not exists (
    select 1 from public.organization_subscriptions s join mp_seed_context c on c.organization_id=s.organization_id
    join public.subscription_plans p on p.code=s.plan_code
    where s.plan_code='full' and s.status='active' and s.starts_at<=now()
      and (s.ends_at is null or s.ends_at>now()) and p.active
  ) then raise exception 'Martinez_Poultry requires an existing active full subscription'; end if;
  if not exists(select 1 from information_schema.columns where table_schema='public' and table_name='lotes' and column_name='is_synthetic') then
    raise exception 'Apply Phase 2 migrations before this seed';
  end if;
end $$;

create temp table mp_seed_farms(ord integer,nombre text,latitud float8,longitud float8,granja_id bigint) on commit drop;
insert into mp_seed_farms(ord,nombre,latitud,longitud) values
(1,'SEMILLA-MP-v1 · San Pedro de los Milagros, Antioquia',6.459,-75.557),
(2,'SEMILLA-MP-v1 · La Ceja, Antioquia',6.031,-75.433),
(3,'SEMILLA-MP-v1 · Fusagasugá, Cundinamarca',4.337,-74.364),
(4,'SEMILLA-MP-v1 · Duitama, Boyacá',5.824,-73.034),
(5,'SEMILLA-MP-v1 · Chinchiná, Caldas',4.982,-75.603);

do $$ declare f record; existing public.granjas; oid uuid; begin
 select organization_id into oid from mp_seed_context;
 for f in select * from mp_seed_farms order by ord loop
  if (select count(*) from public.granjas where organization_id=oid and nombre=f.nombre)>1 then
   raise exception 'Duplicate namespaced farm'; end if;
  select * into existing from public.granjas where organization_id=oid and nombre=f.nombre;
  if found then
   if (existing.latitud,existing.longitud) is distinct from (f.latitud,f.longitud) then
    raise exception 'Namespaced farm was modified: %',f.nombre; end if;
  else
   insert into public.granjas(organization_id,nombre,latitud,longitud) values(oid,f.nombre,f.latitud,f.longitud) returning * into existing;
  end if;
  update mp_seed_farms set granja_id=existing.id where ord=f.ord;
 end loop;
end $$;

create temp table mp_seed_houses on commit drop as
select n as house_num,f.granja_id,'SEMILLA-MP-v1 · Galpón '||lpad(n::text,2,'0') as nombre,
       18000 as capacidad,null::bigint as galpon_id
from generate_series(1,10)n join mp_seed_farms f on f.ord=(n-1)/2+1;
do $$ declare h record; existing public.galpones; begin
 for h in select * from mp_seed_houses order by house_num loop
  if (select count(*) from public.galpones where granja_id=h.granja_id and nombre=h.nombre)>1 then raise exception 'Duplicate namespaced house'; end if;
  select * into existing from public.galpones where granja_id=h.granja_id and nombre=h.nombre;
  if found then
   if existing.capacidad is distinct from h.capacidad then raise exception 'Namespaced house capacity was modified'; end if;
  else
   insert into public.galpones(granja_id,nombre,capacidad) values(h.granja_id,h.nombre,h.capacidad) returning * into existing;
  end if;
  update mp_seed_houses set galpon_id=existing.id where house_num=h.house_num;
 end loop;
end $$;

create temp table mp_seed_lots on commit drop as
with ages as (
 select h.*, (array[5,12,19,26,33,40,5,12,19,26])[h.house_num] as active_age,
        c.snapshot from mp_seed_houses h cross join mp_seed_context c
), scheduled as (
 select a.*,cycle,
   case when cycle=5 then snapshot-active_age+1
        else least(snapshot-active_age+1-15,date '2026-10-31')-41-(4-cycle)*145-(house_num-1)/6 end as placement,
   case when cycle=5 then active_age else 42 end as days
 from ages a cross join generate_series(0,5)cycle
), draws as (
 select s.*,
  ((('x'||substr(md5('MP-v1:weight:u1:'||house_num||':'||cycle),1,8))::bit(32)::bigint)+0.5)/4294967296.0 as u1,
  ((('x'||substr(md5('MP-v1:weight:u2:'||house_num||':'||cycle),1,8))::bit(32)::bigint)+0.5)/4294967296.0 as u2
 from scheduled s
)
select house_num,cycle,galpon_id,
 'SEMILLA-MP-v1-'||lpad(((house_num-1)*6+cycle+1)::text,3,'0') as codigo_lote,
 case when (house_num+cycle)%2=0 then 'Cobb 500' else 'Ross 308' end as linea_genetica,
 placement as fecha_encaste,days,cycle=5 as activo,
 case when cycle<5 then placement+41 end as fecha_cierre,
 (12000+house_num*400+cycle*100)::integer as aves_totales,
 least(2.5,greatest(-2.5,sqrt(-2*ln(u1))*cos(2*pi()*u2)))::numeric as z,
 null::bigint as lote_id
from draws;
alter table mp_seed_lots add column aves_hembra integer;
alter table mp_seed_lots add column aves_macho integer;
update mp_seed_lots set aves_hembra=aves_totales/2,aves_macho=aves_totales-aves_totales/2;
create temp table mp_seed_prior_lots on commit drop as
select l.id from public.lotes l join mp_seed_lots e using(codigo_lote);

do $$ declare l record; existing public.lotes; begin
 for l in select * from mp_seed_lots order by house_num,cycle loop
  if (select count(*) from public.lotes where codigo_lote=l.codigo_lote)>1 then raise exception 'Duplicate namespaced lot'; end if;
  select * into existing from public.lotes where codigo_lote=l.codigo_lote;
  if found then
   if not existing.is_synthetic or
      (existing.galpon_id,existing.fecha_encaste,existing.activo,existing.linea_genetica,existing.aves_totales,existing.aves_hembra,existing.aves_macho,existing.fecha_cierre)
      is distinct from (l.galpon_id,l.fecha_encaste,l.activo,l.linea_genetica,l.aves_totales,l.aves_hembra,l.aves_macho,l.fecha_cierre) then
     raise exception 'Namespaced lot was modified; preserve it and investigate: %',l.codigo_lote;
   end if;
  else
   insert into public.lotes(galpon_id,codigo_lote,linea_genetica,fecha_encaste,aves_hembra,aves_macho,aves_totales,activo,tipo_produccion,proposito,fecha_cierre,motivo_cierre,is_synthetic)
   values(l.galpon_id,l.codigo_lote,l.linea_genetica,l.fecha_encaste,l.aves_hembra,l.aves_macho,l.aves_totales,l.activo,'engorde','Engorde sintético · fotografía 2026-11-21',l.fecha_cierre,
    case when not l.activo then 'Faena completa simulada' end,true) returning * into existing;
  end if;
  update mp_seed_lots set lote_id=existing.id where codigo_lote=l.codigo_lote;
 end loop;
end $$;

create temp table mp_seed_targets(linea text,dia integer,peso numeric,alimento numeric) on commit drop;
insert into mp_seed_targets values
('Cobb 500',0,42,0),('Cobb 500',7,202,180),('Cobb 500',14,570,588),('Cobb 500',21,1116,1320),('Cobb 500',28,1783,2359),('Cobb 500',35,2521,3635),('Cobb 500',42,3278,5100),
('Ross 308',0,44,0),('Ross 308',7,213,166),('Ross 308',14,533,535),('Ross 308',21,1012,1155),('Ross 308',28,1616,2051),('Ross 308',35,2296,3211),('Ross 308',42,2998,4586);

create temp table mp_seed_daily on commit drop as
with curve as (
 select l.*,d,
  lo.peso+(hi.peso-lo.peso)*(d-lo.dia)/greatest(hi.dia-lo.dia,1) as peso_obj,
  lo.alimento+(hi.alimento-lo.alimento)*(d-lo.dia)/greatest(hi.dia-lo.dia,1) as alimento_obj
 from mp_seed_lots l cross join lateral generate_series(1,l.days)d
 join lateral(select * from mp_seed_targets t where t.linea=l.linea_genetica and t.dia<=d order by dia desc limit 1)lo on true
 join lateral(select * from mp_seed_targets t where t.linea=l.linea_genetica and t.dia>=d order by dia limit 1)hi on true
), populations as (
 select c.*,
  round(aves_hembra*(0.025+house_num*0.0005)*d/42.0)::integer as bajas_h,
  round(aves_macho*(0.027+house_num*0.0005)*d/42.0)::integer as bajas_m,
  lag(alimento_obj,1,0::numeric) over(partition by lote_id order by d) as alimento_prev
 from curve c
), values_by_day as (
 select p.*,
  bajas_h-lag(bajas_h,1,0) over(partition by lote_id order by d) as mh,
  bajas_m-lag(bajas_m,1,0) over(partition by lote_id order by d) as mm,
  round((peso_obj*(1+0.09*z)*0.94)::numeric,2) as ph,
  round((peso_obj*(1+0.09*z)*1.06)::numeric,2) as pm,
  round(((alimento_obj-alimento_prev)*(aves_totales-bajas_h-bajas_m)/1000.0*(1+0.09*z))::numeric,2) as ali
 from populations p
)
select lote_id,fecha_encaste+d-1 as fecha,d as dia_vida,mh,mm,ph,pm,
 ((ph*(aves_hembra-bajas_h)+pm*(aves_macho-bajas_m))/(aves_totales-bajas_h-bajas_m))::float8 as peso_mix,
 ali,round((ali*(1.75+house_num*0.015))::numeric,2) as agua,
 activo,days,aves_hembra,aves_macho
from values_by_day;

-- Validate exact existing records before inserting missing rows. Modified user
-- records are never updated by this seed, even in its own reserved namespace.
do $$ begin
 if exists (
  select 1 from public.registros_diarios r join mp_seed_daily e on e.lote_id=r.lote_id and e.fecha=r.fecha
  where r.created_by is not null or
    (r.dia_vida,r.mortalidad_hembra,r.mortalidad_macho,coalesce(r.descarte_hembra,0),coalesce(r.descarte_macho,0),coalesce(r.descartes,0))
    is distinct from (e.dia_vida,e.mh,e.mm,0,0,0)
    or abs(coalesce(r.consumo_alimento_kg,-1)-e.ali)>0.0001
    or abs(coalesce(r.consumo_agua_litros,-1)-e.agua)>0.0001
    or abs(coalesce(r.peso_promedio_mixto_g,-1)-e.peso_mix)>0.0001
    or abs(coalesce(r.peso_promedio_hembra_g,-1)-e.ph)>0.0001
    or abs(coalesce(r.peso_promedio_macho_g,-1)-e.pm)>0.0001
 ) then raise exception 'Namespaced daily data contains manual or differing values'; end if;
 if exists(select 1 from public.registros_diarios r join mp_seed_lots l on l.lote_id=r.lote_id
           where not exists(select 1 from mp_seed_daily e where e.lote_id=r.lote_id and e.fecha=r.fecha)) then
  raise exception 'Namespaced lots have records outside the fixed snapshot'; end if;
 if exists(select 1 from public.lotes l join mp_seed_prior_lots p on p.id=l.id
           join mp_seed_lots e on e.lote_id=l.id
           left join mp_seed_daily d on d.lote_id=l.id and d.dia_vida=42
           where (e.activo and l.peso_cierre_g is not null)
              or (not e.activo and (l.peso_cierre_g is null or abs(l.peso_cierre_g-d.peso_mix)>0.0001))) then
  raise exception 'Namespaced closure weights were modified'; end if;
 if exists(select 1 from public.galpon_boxes b join mp_seed_lots l on l.lote_id=b.lote_id where not l.activo) then
  raise exception 'Closed synthetic lots have unexpected box data'; end if;
end $$;
insert into public.registros_diarios(lote_id,fecha,dia_vida,mortalidad_hembra,mortalidad_macho,descarte_hembra,descarte_macho,descartes,consumo_alimento_kg,consumo_agua_litros,peso_promedio_hembra_g,peso_promedio_macho_g,peso_promedio_mixto_g,created_by)
select lote_id,fecha,dia_vida,mh,mm,0,0,0,ali,agua,ph,pm,peso_mix,null from mp_seed_daily
on conflict(lote_id,fecha) do nothing;
update public.lotes l set peso_cierre_g=e.peso_mix
from mp_seed_daily e where l.id=e.lote_id and not e.activo and e.dia_vida=42 and l.peso_cierre_g is null
  and not exists(select 1 from mp_seed_prior_lots p where p.id=l.id);

-- One mixed-sex box per active lot represents the entire lot population.
create temp table mp_seed_active_boxes on commit drop as
select l.lote_id,l.aves_hembra,l.aves_macho,null::bigint as box_id from mp_seed_lots l where l.activo;
do $$ declare b record; existing public.galpon_boxes; begin
 for b in select * from mp_seed_active_boxes order by lote_id loop
  if (select count(*) from public.galpon_boxes where lote_id=b.lote_id)>1 then raise exception 'Active seed lot boxes were reconfigured'; end if;
  select * into existing from public.galpon_boxes where lote_id=b.lote_id;
  if found then
   if (existing.nombre_box,existing.aves_hembra_inicial,existing.aves_macho_inicial) is distinct from ('Box sintético único',b.aves_hembra,b.aves_macho) then raise exception 'Active seed box was modified'; end if;
  else
   insert into public.galpon_boxes(lote_id,nombre_box,aves_hembra_inicial,aves_macho_inicial)
   values(b.lote_id,'Box sintético único',b.aves_hembra,b.aves_macho) returning * into existing;
  end if;
  update mp_seed_active_boxes set box_id=existing.id where lote_id=b.lote_id;
 end loop;
end $$;

do $$ begin
 if exists (
  select 1 from public.registros_diarios_box b join mp_seed_active_boxes s on s.box_id=b.box_id
  join public.registros_diarios r on r.id=b.registro_diario_id
  join mp_seed_daily e on e.lote_id=r.lote_id and e.fecha=r.fecha
  where b.created_by is not null or (b.mortalidad_hembra,b.mortalidad_macho,b.descarte_hembra,b.descarte_macho)
    is distinct from (e.mh,e.mm,0,0)
    or abs(coalesce(b.consumo_alimento_kg,-1)-e.ali)>0.0001
    or abs(coalesce(b.consumo_agua_litros,-1)-e.agua)>0.0001
    or abs(coalesce(b.peso_promedio_hembra_g,-1)-e.ph)>0.0001
    or abs(coalesce(b.peso_promedio_macho_g,-1)-e.pm)>0.0001
 ) then raise exception 'Namespaced daily box data was modified'; end if;
end $$;
insert into public.registros_diarios_box(registro_diario_id,box_id,mortalidad_hembra,mortalidad_macho,descarte_hembra,descarte_macho,consumo_alimento_kg,consumo_agua_litros,peso_promedio_hembra_g,peso_promedio_macho_g,created_by)
select r.id,b.box_id,e.mh,e.mm,0,0,e.ali,e.agua,e.ph,e.pm,null
from mp_seed_daily e join mp_seed_active_boxes b using(lote_id)
join public.registros_diarios r on r.lote_id=e.lote_id and r.fecha=e.fecha
where not exists(select 1 from public.registros_diarios_box x where x.registro_diario_id=r.id and x.box_id=b.box_id)
on conflict(registro_diario_id,box_id) do nothing;

-- Biological/calendar invariants. Failure aborts the whole seed.
do $$ begin
 if (select count(*) from mp_seed_lots)<>60 or (select count(*) from mp_seed_lots where activo)<>10
    or (select count(*) from mp_seed_daily)<>2297 then raise exception 'Unexpected seed cardinality'; end if;
 if exists(select 1 from mp_seed_daily cross join mp_seed_context where fecha>snapshot or ali<0 or agua<0 or peso_mix<=0) then raise exception 'Invalid synthetic daily values'; end if;
 if exists(select 1 from mp_seed_lots where aves_totales>18000 or fecha_encaste<date '2025-01-01' or (not activo and (fecha_cierre>date '2026-10-31' or fecha_cierre-fecha_encaste<>41))) then raise exception 'Invalid cycle or capacity'; end if;
 if exists(select 1 from (
   select *,lag(coalesce(fecha_cierre,date '2026-11-21')) over(partition by galpon_id order by fecha_encaste) as previous_end from mp_seed_lots
 ) x where previous_end is not null and fecha_encaste-previous_end-1<14) then raise exception 'Cycle overlap or insufficient sanitary downtime'; end if;
 if (select count(*) from public.registros_diarios r join mp_seed_lots l on l.lote_id=r.lote_id)<>2297 then raise exception 'Missing synthetic daily records'; end if;
 if (select count(*) from public.registros_diarios_box b join mp_seed_active_boxes a on a.box_id=b.box_id)<>197 then raise exception 'Missing active box details'; end if;
end $$;

select 60 as lotes_sinteticos,50 as cerrados,10 as activos,2297 as registros_diarios,
       date '2026-11-21' as fecha_fotografia;
drop table mp_seed_active_boxes,mp_seed_daily,mp_seed_targets,mp_seed_prior_lots,mp_seed_lots,mp_seed_houses,mp_seed_farms,mp_seed_context;
commit;
