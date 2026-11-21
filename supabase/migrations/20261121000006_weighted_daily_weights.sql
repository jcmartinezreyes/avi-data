-- Population-weighted sex and mixed weights at each measurement date.
-- Prerequisites: phases 1 and 2. Execute as one migration transaction.
-- The population proxy is end-of-day live birds per box; sample sizes are unavailable.
-- Missing measurements for a populated sex produce NULL, not a fabricated zero.
lock table public.registros_diarios_box in share row exclusive mode;

create or replace function private.lock_weighted_weight_lots()
returns trigger language plpgsql security invoker set search_path='' as $$
declare
  v_old_daily_id bigint;
  v_new_daily_id bigint;
  v_old_box_id bigint;
  v_new_box_id bigint;
  v_lote_ids bigint[];
begin
  if tg_op <> 'INSERT' then
    v_old_daily_id:=old.registro_diario_id;
    v_old_box_id:=old.box_id;
  end if;
  if tg_op <> 'DELETE' then
    v_new_daily_id:=new.registro_diario_id;
    v_new_box_id:=new.box_id;
  end if;
  select array_agg(distinct lot_id order by lot_id) into v_lote_ids
  from (
    select d.lote_id as lot_id from public.registros_diarios d
      where d.id=any(array[v_old_daily_id,v_new_daily_id])
    union
    select b.lote_id from public.galpon_boxes b
      where b.id=any(array[v_old_box_id,v_new_box_id])
  ) lots;
  -- Match the lot lock used by closing and daily-capture RPCs, before header locks.
  perform l.id from public.lotes l where l.id=any(v_lote_ids)
  order by l.id for no key update;
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$$;

create or replace function private.sync_weighted_daily_weights()
returns trigger language plpgsql security invoker set search_path='' as $$
declare
  v_old_daily_id bigint;
  v_new_daily_id bigint;
  v_old_box_id bigint;
  v_new_box_id bigint;
  v_lote_ids bigint[];
begin
  if tg_op <> 'INSERT' then
    v_old_daily_id:=old.registro_diario_id;
    v_old_box_id:=old.box_id;
  end if;
  if tg_op <> 'DELETE' then
    v_new_daily_id:=new.registro_diario_id;
    v_new_box_id:=new.box_id;
  end if;
  select array_agg(distinct lot_id order by lot_id) into v_lote_ids
  from (
    select d.lote_id as lot_id from public.registros_diarios d
      where d.id=any(array[v_old_daily_id,v_new_daily_id])
    union
    select b.lote_id from public.galpon_boxes b
      where b.id=any(array[v_old_box_id,v_new_box_id])
  ) lots;
  -- Earlier mortality edits affect all later weighings in the lot.
with relevant_headers as (
  select d.id, d.lote_id, d.fecha
  from public.registros_diarios d
  where d.lote_id = any(v_lote_ids)
    and exists (
      select 1 from public.registros_diarios_box r where r.registro_diario_id=d.id
    )
), populations as (
  select d.id, b.id as box_id,
    greatest(coalesce(b.aves_hembra_inicial,0) - coalesce(losses.hembras,0),0) as hembras,
    greatest(coalesce(b.aves_macho_inicial,0) - coalesce(losses.machos,0),0) as machos,
    nullif(r.peso_promedio_hembra_g,0) as peso_h,
    nullif(r.peso_promedio_macho_g,0) as peso_m
  from relevant_headers d
  join public.galpon_boxes b on b.lote_id=d.lote_id
  left join public.registros_diarios_box r on r.registro_diario_id=d.id and r.box_id=b.id
  left join lateral (
    select sum(coalesce(prev.mortalidad_hembra,0)+coalesce(prev.descarte_hembra,0)) as hembras,
           sum(coalesce(prev.mortalidad_macho,0)+coalesce(prev.descarte_macho,0)) as machos
    from public.registros_diarios_box prev
    join public.registros_diarios pd on pd.id=prev.registro_diario_id
    where prev.box_id=b.id and pd.fecha<=d.fecha
  ) losses on true
), aggregates as (
  select id, sum(hembras) as hembras, sum(machos) as machos,
    sum(peso_h*hembras) as masa_h, sum(peso_m*machos) as masa_m,
    bool_or(hembras>0 and (peso_h is null or peso_h<=0)) as missing_h,
    bool_or(machos>0 and (peso_m is null or peso_m<=0)) as missing_m
  from populations group by id
), weighted as (
  select id,
    case when hembras>0 and not missing_h then masa_h/hembras end as peso_h,
    case when machos>0 and not missing_m then masa_m/machos end as peso_m,
    case when hembras+machos>0 and not missing_h and not missing_m
      then (coalesce(masa_h,0)+coalesce(masa_m,0))/(hembras+machos) end as peso_mix
  from aggregates
)
update public.registros_diarios d
set peso_promedio_hembra_g=w.peso_h,
    peso_promedio_macho_g=w.peso_m,
    peso_promedio_mixto_g=w.peso_mix
from weighted w where w.id=d.id;
  -- Only a header touched by this mutation loses its weights when its final
  -- measurement disappears. Unrelated legacy consolidated headers stay intact.
  update public.registros_diarios d
  set peso_promedio_hembra_g=null, peso_promedio_macho_g=null,
      peso_promedio_mixto_g=null
  where d.id=any(array[v_old_daily_id,v_new_daily_id])
    and not exists(select 1 from public.registros_diarios_box r where r.registro_diario_id=d.id);
  return null;
end;
$$;
revoke all on function private.lock_weighted_weight_lots() from public,anon,authenticated;
revoke all on function private.sync_weighted_daily_weights() from public,anon,authenticated;

-- PostgreSQL runs same-event row triggers in name order. Lock lot before phase 2
-- locks daily parents, and apply weighted values after its aggregate update.
create trigger aaa_lock_weighted_weight_lots
before insert or update or delete on public.registros_diarios_box
for each row execute function private.lock_weighted_weight_lots();
create trigger zzz_sync_weighted_daily_weights
 after insert or update or delete on public.registros_diarios_box
for each row execute function private.sync_weighted_daily_weights();

-- Recompute only headers with details, preserving consolidated legacy records.
do $$
declare v_lote_ids bigint[];
begin
  select array_agg(distinct d.lote_id) into v_lote_ids
  from public.registros_diarios d
  where exists(select 1 from public.registros_diarios_box r where r.registro_diario_id=d.id);
with relevant_headers as (
  select d.id, d.lote_id, d.fecha
  from public.registros_diarios d
  where d.lote_id = any(v_lote_ids)
    and exists (
      select 1 from public.registros_diarios_box r where r.registro_diario_id=d.id
    )
), populations as (
  select d.id, b.id as box_id,
    greatest(coalesce(b.aves_hembra_inicial,0) - coalesce(losses.hembras,0),0) as hembras,
    greatest(coalesce(b.aves_macho_inicial,0) - coalesce(losses.machos,0),0) as machos,
    nullif(r.peso_promedio_hembra_g,0) as peso_h,
    nullif(r.peso_promedio_macho_g,0) as peso_m
  from relevant_headers d
  join public.galpon_boxes b on b.lote_id=d.lote_id
  left join public.registros_diarios_box r on r.registro_diario_id=d.id and r.box_id=b.id
  left join lateral (
    select sum(coalesce(prev.mortalidad_hembra,0)+coalesce(prev.descarte_hembra,0)) as hembras,
           sum(coalesce(prev.mortalidad_macho,0)+coalesce(prev.descarte_macho,0)) as machos
    from public.registros_diarios_box prev
    join public.registros_diarios pd on pd.id=prev.registro_diario_id
    where prev.box_id=b.id and pd.fecha<=d.fecha
  ) losses on true
), aggregates as (
  select id, sum(hembras) as hembras, sum(machos) as machos,
    sum(peso_h*hembras) as masa_h, sum(peso_m*machos) as masa_m,
    bool_or(hembras>0 and (peso_h is null or peso_h<=0)) as missing_h,
    bool_or(machos>0 and (peso_m is null or peso_m<=0)) as missing_m
  from populations group by id
), weighted as (
  select id,
    case when hembras>0 and not missing_h then masa_h/hembras end as peso_h,
    case when machos>0 and not missing_m then masa_m/machos end as peso_m,
    case when hembras+machos>0 and not missing_h and not missing_m
      then (coalesce(masa_h,0)+coalesce(masa_m,0))/(hembras+machos) end as peso_mix
  from aggregates
)
update public.registros_diarios d
set peso_promedio_hembra_g=w.peso_h,
    peso_promedio_macho_g=w.peso_m,
    peso_promedio_mixto_g=w.peso_mix
from weighted w where w.id=d.id;
end;
$$;
