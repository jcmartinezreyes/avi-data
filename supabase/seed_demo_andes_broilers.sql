-- Synthetic demonstration data for Martinez_Poultry.
-- These production measurements are interpolated from published Cobb 500 and
-- Ross 308 targets; they are not real farm records or veterinary guidance.
-- Geography: five sample farms in Colombia's Andean region.

-- Fixed demonstration snapshot so a repeat run does not shift the calendar.
begin;

create temp table avi_demo_specs on commit drop as
with
org as (
    select id from public.organizations where name = 'Martinez_Poultry'
),
farm_specs(ord, nombre, latitud, longitud) as (
    values
      (1, 'Demo Andino - San Pedro de los Milagros, Antioquia', 6.4590::double precision, -75.5570::double precision),
      (2, 'Demo Andino - La Ceja, Antioquia', 6.0310::double precision, -75.4330::double precision),
      (3, 'Demo Andino - Fusagasuga, Cundinamarca', 4.3370::double precision, -74.3640::double precision),
      (4, 'Demo Andino - Duitama, Boyaca', 5.8240::double precision, -73.0340::double precision),
      (5, 'Demo Andino - Chinchina, Caldas', 4.9820::double precision, -75.6030::double precision)
),
inserted_farms as (
    insert into public.granjas (organization_id, nombre, latitud, longitud)
    select org.id, fs.nombre, fs.latitud, fs.longitud
    from org cross join farm_specs fs
    where not exists (
      select 1 from public.granjas f
      where f.organization_id = org.id and f.nombre = fs.nombre
    )
    returning id, nombre
),
all_farms as (
    select fs.ord, f.id, fs.nombre from inserted_farms f join farm_specs fs using (nombre)
    union all
    select fs.ord, f.id, fs.nombre
    from org cross join farm_specs fs
    join public.granjas f on f.organization_id = org.id and f.nombre = fs.nombre
    where not exists (select 1 from inserted_farms i where i.nombre = fs.nombre)
),
house_specs as (
    select f.ord as farm_ord, f.id as granja_id, n as house_ord,
           'Galpon ' || lpad(n::text, 2, '0') as nombre
    from all_farms f cross join generate_series(1, 10) n
),
inserted_houses as (
    insert into public.galpones (granja_id, nombre, capacidad)
    select hs.granja_id, hs.nombre, 18000
    from house_specs hs
    where not exists (
      select 1 from public.galpones g
      where g.granja_id = hs.granja_id and g.nombre = hs.nombre
    )
    returning id, granja_id, nombre
),
all_houses as (
    select hs.farm_ord, hs.house_ord, h.id, h.granja_id, h.nombre
    from inserted_houses h join house_specs hs on hs.granja_id = h.granja_id and hs.nombre = h.nombre
    union all
    select hs.farm_ord, hs.house_ord, h.id, h.granja_id, h.nombre
    from house_specs hs join public.galpones h on h.granja_id = hs.granja_id and h.nombre = hs.nombre
    where not exists (select 1 from inserted_houses i where i.id = h.id)
)
select n as lot_num, 'DEMO-AVI-2026-' || lpad(n::text, 3, '0') as codigo_lote,
       h.id as galpon_id,
       case when n % 2 = 0 then 'Cobb 500' else 'Ross 308' end as linea_genetica,
       -- Avoid the existing organization's placement dates in this snapshot.
       case when n = 28 then date '2026-07-31'
            when n = 44 then date '2026-09-03'
            when n <= 50 then date '2026-11-05' - (150 - 2 * (n - 1))
            else date '2026-11-05' - (5 + 5 * (n - 51)) end as fecha_encaste,
       n > 50 as activo,
       case when n <= 50 then 42 else 5 + 5 * (n - 51) end as dias_registrados
from generate_series(1, 57) n
join all_houses h
  on h.farm_ord = case when n <= 50 then (n - 1) / 10 + 1 else (n - 51) % 5 + 1 end
 and h.house_ord = case when n <= 50 then (n - 1) % 10 + 1 else (n - 51) / 5 + 1 end;

-- Keep the original lot and daily record IDs. Only move the original demo rows.
do $$
begin
    if (select count(*) from avi_demo_specs) <> 57 then
        raise exception 'Expected exactly 57 demo lot specifications';
    end if;
    if exists (
        select 1 from avi_demo_specs s join public.lotes l using (codigo_lote)
        where l.galpon_id is distinct from s.galpon_id
    ) or exists (
        select 1 from avi_demo_specs s join public.lotes l using (codigo_lote)
        where not s.activo and l.fecha_encaste <> s.fecha_encaste
          and (exists (select 1 from public.galpon_boxes b where b.lote_id = l.id)
            or exists (select 1 from public.registros_diarios r
                       where r.lote_id = l.id and r.created_by is not null))
    ) then
        raise exception 'Demo lot data differs from the original seed';
    end if;
end $$;

update public.registros_diarios r
set fecha = date '1900-01-01' + r.dia_vida - 1
from avi_demo_specs s join public.lotes l using (codigo_lote)
where r.lote_id = l.id and not s.activo and l.fecha_encaste <> s.fecha_encaste;

update public.registros_diarios r
set fecha = s.fecha_encaste + r.dia_vida - 1
from avi_demo_specs s join public.lotes l using (codigo_lote)
where r.lote_id = l.id and not s.activo and l.fecha_encaste <> s.fecha_encaste;

-- Stage the date change first because the old and new date ranges can overlap.
update public.registros_diarios r
set fecha = s.fecha_encaste + r.dia_vida - 1
from avi_demo_specs s join public.lotes l using (codigo_lote)
where r.lote_id = l.id and not s.activo and l.fecha_encaste <> s.fecha_encaste;

update public.lotes l
set fecha_encaste = s.fecha_encaste, activo = false
from avi_demo_specs s
where l.codigo_lote = s.codigo_lote and not s.activo
  and (l.fecha_encaste is distinct from s.fecha_encaste or l.activo is distinct from false);

insert into public.lotes (
  galpon_id, codigo_lote, linea_genetica, fecha_encaste,
  aves_hembra, aves_macho, aves_totales, activo, proposito, tipo_produccion
)
select galpon_id, codigo_lote, linea_genetica, fecha_encaste,
       7500, 7500, 15000, activo, 'Engorde de demostracion', 'engorde'
from avi_demo_specs s
where not exists (select 1 from public.lotes l where l.codigo_lote = s.codigo_lote);

with
targets(linea_genetica, dia, peso_g, alimento_acumulado_g) as (
    values
      ('Cobb 500',  0,   42.0,    0.0),
      ('Cobb 500',  7,  202.0,  179.0),
      ('Cobb 500', 14,  570.0,  587.0),
      ('Cobb 500', 21, 1115.5, 1319.0),
      ('Cobb 500', 28, 1783.0, 2357.5),
      ('Cobb 500', 35, 2521.0, 3633.5),
      ('Cobb 500', 42, 3277.5, 5097.5),
      ('Ross 308',  0,   44.0,    0.0),
      ('Ross 308',  7,  213.0,  166.0),
      ('Ross 308', 14,  533.0,  535.0),
      ('Ross 308', 21, 1012.0, 1155.0),
      ('Ross 308', 28, 1616.0, 2051.0),
      ('Ross 308', 35, 2296.0, 3211.0),
      ('Ross 308', 42, 2998.0, 4586.0)
),
ages as (
    select l.id, s.linea_genetica, s.fecha_encaste, s.lot_num, l.aves_totales, d as dia
    from avi_demo_specs s join public.lotes l using (codigo_lote)
    cross join lateral generate_series(1, s.dias_registrados) d
),
interpolated as (
    select a.*,
           lo.peso_g + (a.dia - lo.dia) * (hi.peso_g - lo.peso_g) / greatest(hi.dia - lo.dia, 1) as peso_g,
           lo.alimento_acumulado_g + (a.dia - lo.dia) *
             (hi.alimento_acumulado_g - lo.alimento_acumulado_g) / greatest(hi.dia - lo.dia, 1) as alimento_g
    from ages a
    join lateral (
      select t.* from targets t where t.linea_genetica = a.linea_genetica and t.dia <= a.dia
      order by t.dia desc limit 1
    ) lo on true
    join lateral (
      select t.* from targets t where t.linea_genetica = a.linea_genetica and t.dia >= a.dia
      order by t.dia limit 1
    ) hi on true
),
daily as (
    select i.*, (i.alimento_g - lag(i.alimento_g, 1, 0) over (partition by i.id order by i.dia))
      * greatest(i.aves_totales - i.dia * 4, 1) / 1000.0
      * (0.96 + (i.lot_num % 9) * 0.01) as alimento_kg,
      i.peso_g * (0.955 + (i.lot_num % 10) * 0.01) as peso_demo
    from interpolated i
)
insert into public.registros_diarios (
  lote_id, fecha, dia_vida, mortalidad_hembra, mortalidad_macho, descartes,
  descarte_hembra, descarte_macho, consumo_alimento_kg, consumo_agua_litros,
  peso_promedio_mixto_g, peso_promedio_hembra_g, peso_promedio_macho_g
)
select id, fecha_encaste + dia - 1, dia,
       1 + (dia + lot_num) % 3, 1 + (dia + 2 * lot_num) % 4, 0, 0, 0,
       round(alimento_kg::numeric, 2), round((alimento_kg * (1.7 + (lot_num % 5) * 0.05))::numeric, 2),
       round(peso_demo::numeric, 1), round((peso_demo * 0.94)::numeric, 1), round((peso_demo * 1.06)::numeric, 1)
from daily
on conflict (lote_id, fecha) do update set
  mortalidad_hembra = excluded.mortalidad_hembra, mortalidad_macho = excluded.mortalidad_macho,
  consumo_alimento_kg = excluded.consumo_alimento_kg, consumo_agua_litros = excluded.consumo_agua_litros,
  peso_promedio_mixto_g = excluded.peso_promedio_mixto_g,
  peso_promedio_hembra_g = excluded.peso_promedio_hembra_g, peso_promedio_macho_g = excluded.peso_promedio_macho_g
where registros_diarios.created_by is null
  and not exists (select 1 from public.registros_diarios_box b where b.registro_diario_id = registros_diarios.id);

insert into public.galpon_boxes (lote_id, nombre_box, aves_hembra_inicial, aves_macho_inicial)
select l.id, 'Box demo', l.aves_hembra, l.aves_macho
from avi_demo_specs s join public.lotes l using (codigo_lote)
where s.activo and l.activo and not exists (select 1 from public.galpon_boxes b where b.lote_id = l.id);

insert into public.registros_diarios_box (
  registro_diario_id, box_id, mortalidad_hembra, mortalidad_macho, descarte_hembra, descarte_macho,
  consumo_alimento_kg, consumo_agua_litros, peso_promedio_hembra_g, peso_promedio_macho_g
)
select r.id, b.id, r.mortalidad_hembra, r.mortalidad_macho, r.descarte_hembra, r.descarte_macho,
       r.consumo_alimento_kg, r.consumo_agua_litros, r.peso_promedio_hembra_g, r.peso_promedio_macho_g
from avi_demo_specs s join public.lotes l using (codigo_lote)
join public.galpon_boxes b on b.lote_id = l.id and b.nombre_box = 'Box demo'
join public.registros_diarios r on r.lote_id = l.id and r.created_by is null
where s.activo and l.activo
on conflict (registro_diario_id, box_id) do nothing;

commit;
