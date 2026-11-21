-- Phase 2.3: persist consolidated daily values without bypassing RLS.
-- Run the migration inside a transaction. Block detail writes while installing
-- the triggers and backfilling only headers that already have box detail.
lock table public.registros_diarios_box in share row exclusive mode;

create or replace function private.lock_daily_totals_parents()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_old_daily_id bigint;
  v_new_daily_id bigint;
begin
  if tg_op <> 'INSERT' then
    v_old_daily_id := old.registro_diario_id;
  end if;
  if tg_op <> 'DELETE' then
    v_new_daily_id := new.registro_diario_id;
  end if;

  -- Serialize writers for the same daily header before changing its details.
  -- NO KEY UPDATE still permits the FK's KEY SHARE lock. Sorting both parents
  -- makes a transfer between two headers acquire its parent locks consistently.
  perform d.id
  from public.registros_diarios d
  where d.id = any(array[v_old_daily_id, v_new_daily_id])
  order by d.id
  for no key update;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create or replace function private.sync_daily_totals_from_boxes()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_old_daily_id bigint;
  v_new_daily_id bigint;
  v_daily_id bigint;
begin
  if tg_op <> 'INSERT' then
    v_old_daily_id := old.registro_diario_id;
  end if;
  if tg_op <> 'DELETE' then
    v_new_daily_id := new.registro_diario_id;
  end if;

  -- Recompute both sides of a transfer. An empty aggregate produces zero totals
  -- when the last detail is removed. A parent deleted by cascade is simply absent.
  for v_daily_id in
    select distinct parent_id
    from unnest(array[v_old_daily_id, v_new_daily_id]) as parents(parent_id)
    where parent_id is not null
    order by parent_id
  loop
    update public.registros_diarios d
    set
      mortalidad_hembra = sub.tot_mh,
      mortalidad_macho = sub.tot_mm,
      descarte_hembra = sub.tot_dh,
      descarte_macho = sub.tot_dm,
      descartes = sub.tot_dh + sub.tot_dm,
      consumo_alimento_kg = sub.tot_ali,
      consumo_agua_litros = sub.tot_agu,
      peso_promedio_hembra_g = sub.avg_ph,
      peso_promedio_macho_g = sub.avg_pm,
      peso_promedio_mixto_g = case
        when sub.avg_ph > 0 and sub.avg_pm > 0 then (sub.avg_ph + sub.avg_pm) / 2
        else coalesce(nullif(sub.avg_ph, 0), sub.avg_pm, 0)
      end
    from (
      select
        coalesce(sum(b.mortalidad_hembra), 0) as tot_mh,
        coalesce(sum(b.mortalidad_macho), 0) as tot_mm,
        coalesce(sum(b.descarte_hembra), 0) as tot_dh,
        coalesce(sum(b.descarte_macho), 0) as tot_dm,
        coalesce(sum(b.consumo_alimento_kg), 0) as tot_ali,
        coalesce(sum(b.consumo_agua_litros), 0) as tot_agu,
        coalesce(avg(nullif(b.peso_promedio_hembra_g, 0)), 0) as avg_ph,
        coalesce(avg(nullif(b.peso_promedio_macho_g, 0)), 0) as avg_pm
      from public.registros_diarios_box b
      where b.registro_diario_id = v_daily_id
    ) sub
    where d.id = v_daily_id;
  end loop;

  return null;
end;
$$;

-- These functions are trigger-only, not user-callable mutation endpoints.
revoke all on function private.lock_daily_totals_parents() from public, anon, authenticated;
revoke all on function private.sync_daily_totals_from_boxes() from public, anon, authenticated;

drop trigger if exists trg_lock_daily_totals_parents on public.registros_diarios_box;
create trigger trg_lock_daily_totals_parents
before insert or update or delete on public.registros_diarios_box
for each row execute function private.lock_daily_totals_parents();

drop trigger if exists trg_sync_daily_totals on public.registros_diarios_box;
create trigger trg_sync_daily_totals
after insert or update or delete on public.registros_diarios_box
for each row execute function private.sync_daily_totals_from_boxes();

-- Preserve consolidated legacy records that have no box-level measurements.
-- Phase 3 will revise the weight formulas to use the agreed population weights.
with totals as (
  select
    b.registro_diario_id,
    coalesce(sum(b.mortalidad_hembra), 0) as tot_mh,
    coalesce(sum(b.mortalidad_macho), 0) as tot_mm,
    coalesce(sum(b.descarte_hembra), 0) as tot_dh,
    coalesce(sum(b.descarte_macho), 0) as tot_dm,
    coalesce(sum(b.consumo_alimento_kg), 0) as tot_ali,
    coalesce(sum(b.consumo_agua_litros), 0) as tot_agu,
    coalesce(avg(nullif(b.peso_promedio_hembra_g, 0)), 0) as avg_ph,
    coalesce(avg(nullif(b.peso_promedio_macho_g, 0)), 0) as avg_pm
  from public.registros_diarios_box b
  group by b.registro_diario_id
)
update public.registros_diarios d
set
  mortalidad_hembra = totals.tot_mh,
  mortalidad_macho = totals.tot_mm,
  descarte_hembra = totals.tot_dh,
  descarte_macho = totals.tot_dm,
  descartes = totals.tot_dh + totals.tot_dm,
  consumo_alimento_kg = totals.tot_ali,
  consumo_agua_litros = totals.tot_agu,
  peso_promedio_hembra_g = totals.avg_ph,
  peso_promedio_macho_g = totals.avg_pm,
  peso_promedio_mixto_g = case
    when totals.avg_ph > 0 and totals.avg_pm > 0 then (totals.avg_ph + totals.avg_pm) / 2
    else coalesce(nullif(totals.avg_ph, 0), totals.avg_pm, 0)
  end
from totals
where d.id = totals.registro_diario_id;
