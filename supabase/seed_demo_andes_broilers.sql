-- Synthetic demonstration data for Martinez_Poultry.
-- These production measurements are interpolated from published Cobb 500 and
-- Ross 308 targets; they are not real farm records or veterinary guidance.
-- Geography: five sample farms in Colombia's Andean region.

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
),
lot_specs as (
    select n as lot_num,
           'DEMO-AVI-2026-' || lpad(n::text, 3, '0') as codigo_lote,
           h.id as galpon_id,
           case when n % 2 = 0 then 'Cobb 500' else 'Ross 308' end as linea_genetica,
           (14 + ((n - 1) % 5) * 7)::integer as edad_dias
    from generate_series(1, 50) n
    join all_houses h
      on h.farm_ord = ((n - 1) / 10) + 1
     and h.house_ord = ((n - 1) % 10) + 1
),
inserted_lots as (
    insert into public.lotes (
      galpon_id, codigo_lote, linea_genetica, fecha_encaste,
      aves_hembra, aves_macho, aves_totales, activo, proposito, tipo_produccion
    )
    select galpon_id, codigo_lote, linea_genetica, current_date - edad_dias,
           7500, 7500, 15000, true, 'Engorde de demostracion', 'engorde'
    from lot_specs s
    where not exists (select 1 from public.lotes l where l.codigo_lote = s.codigo_lote)
    returning id, codigo_lote, galpon_id, linea_genetica, fecha_encaste,
              aves_hembra, aves_macho, aves_totales
),
all_demo_lots as (
    select id, codigo_lote, galpon_id, linea_genetica, fecha_encaste,
           aves_hembra, aves_macho, aves_totales
    from inserted_lots
    union all
    select l.id, l.codigo_lote, l.galpon_id, l.linea_genetica, l.fecha_encaste,
           l.aves_hembra, l.aves_macho, l.aves_totales
    from public.lotes l
    where l.codigo_lote like 'DEMO-AVI-2026-%'
      and not exists (select 1 from inserted_lots i where i.id = l.id)
),
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
    select l.*,
           (current_date - l.fecha_encaste)::integer as edad_actual,
           d as dia
    from all_demo_lots l
    cross join lateral generate_series(1, least(42, (current_date - l.fecha_encaste)::integer)) d
),
interpolated as (
    select a.*,
           lo.dia as dia_anterior,
           case when hi.dia = lo.dia then lo.peso_g
                else lo.peso_g + (a.dia - lo.dia) * (hi.peso_g - lo.peso_g) / (hi.dia - lo.dia)
           end as peso_objetivo_g,
           case when hi.dia = lo.dia then lo.alimento_acumulado_g
                else lo.alimento_acumulado_g + (a.dia - lo.dia) *
                  (hi.alimento_acumulado_g - lo.alimento_acumulado_g) / (hi.dia - lo.dia)
           end as alimento_acum_objetivo_g
    from ages a
    join lateral (
      select t.* from targets t
      where t.linea_genetica = a.linea_genetica and t.dia <= a.dia
      order by t.dia desc limit 1
    ) lo on true
    join lateral (
      select t.* from targets t
      where t.linea_genetica = a.linea_genetica and t.dia >= a.dia
      order by t.dia limit 1
    ) hi on true
),
daily_values as (
    select i.*,
           coalesce(lag(i.alimento_acum_objetivo_g) over (partition by i.id order by i.dia), 0) as alimento_acum_previo_g
    from interpolated i
),
inserted_daily as (
    insert into public.registros_diarios (
      lote_id, fecha, dia_vida, mortalidad_hembra, mortalidad_macho,
      descartes, descarte_hembra, descarte_macho, consumo_alimento_kg,
      consumo_agua_litros, peso_promedio_mixto_g
    )
    select id, fecha_encaste + dia, dia_vida,
           case when dia % 7 = 0 then 2 else 1 end,
           case when dia % 5 = 0 then 2 else 1 end,
           0, 0, 0,
           round(((alimento_acum_objetivo_g - alimento_acum_previo_g) *
             greatest(aves_totales - dia * 2, 1) / 1000.0)::numeric, 2),
           round(((alimento_acum_objetivo_g - alimento_acum_previo_g) *
             greatest(aves_totales - dia * 2, 1) * 1.8 / 1000.0)::numeric, 2),
           round(peso_objetivo_g::numeric, 1)
    from (
      select d.*, d.dia as dia_vida from daily_values d
    ) values_to_insert
    on conflict (lote_id, fecha) do update set
      dia_vida = excluded.dia_vida,
      mortalidad_hembra = excluded.mortalidad_hembra,
      mortalidad_macho = excluded.mortalidad_macho,
      descartes = excluded.descartes,
      descarte_hembra = excluded.descarte_hembra,
      descarte_macho = excluded.descarte_macho,
      consumo_alimento_kg = excluded.consumo_alimento_kg,
      consumo_agua_litros = excluded.consumo_agua_litros,
      peso_promedio_mixto_g = excluded.peso_promedio_mixto_g
    returning id
)
select
  (select count(*) from all_farms) as granjas_andinas,
  (select count(*) from all_houses) as galpones_demo,
  (select count(*) from all_demo_lots) as lotes_demo,
  (select count(*) from inserted_daily) as registros_diarios_creados;
