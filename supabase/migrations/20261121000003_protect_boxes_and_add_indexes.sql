-- Protect both kinds of historical box measurements against cascading deletion.
alter table public.mediciones_produccion
  drop constraint mediciones_produccion_box_id_fkey,
  add constraint mediciones_produccion_box_id_fkey
    foreign key (box_id) references public.galpon_boxes(id) on delete restrict;
alter table public.registros_diarios_box
  drop constraint registros_diarios_box_box_id_fkey,
  add constraint registros_diarios_box_box_id_fkey
    foreign key (box_id) references public.galpon_boxes(id) on delete restrict;

-- Reuse the index names present in the hosted database.
create index if not exists idx_galpon_boxes_lote_id on public.galpon_boxes(lote_id);
create index if not exists idx_registros_diarios_box_box_id on public.registros_diarios_box(box_id);
create index if not exists registros_diarios_lote_dia_idx on public.registros_diarios(lote_id, dia_vida);

alter table public.lotes
  add column if not exists fecha_cierre date,
  add column if not exists motivo_cierre text,
  add column if not exists peso_cierre_g numeric,
  add column if not exists is_synthetic boolean not null default false;

-- A SELECT helper that queries the new lot by ID cannot see it in the statement
-- snapshot during INSERT ... RETURNING. Authorize its existing destination farm
-- instead. This retains organization isolation and permits atomic lot creation.
alter policy lotes_select on public.lotes
  using (private.user_can_access_farm(
    (select g.granja_id from public.galpones g where g.id = lotes.galpon_id), false
  ));

-- One API call is one transaction: no partial lot/box configuration can persist.
create or replace function public.save_lote_with_boxes(
  p_lote jsonb, p_boxes jsonb, p_lote_id bigint default null
)
returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_lote_id bigint := p_lote_id;
  v_activo boolean;
  v_box jsonb;
  v_hembras bigint;
  v_machos bigint;
  v_count integer;
  v_ids bigint[];
  v_granja_id bigint;
begin
  if auth.uid() is null then
    raise exception 'Authentication required' using errcode = '42501';
  end if;
  if jsonb_typeof(p_lote) is distinct from 'object'
     or jsonb_typeof(p_boxes) is distinct from 'array' then
    raise exception 'Expected lot object and box array' using errcode = '22023';
  end if;
  if jsonb_array_length(p_boxes) not between 1 and 30
     or nullif(btrim(p_lote->>'codigo_lote'), '') is null
     or nullif(p_lote->>'fecha_encaste', '') is null then
    raise exception 'A lot code, placement date and 1 to 30 boxes are required' using errcode = '22023';
  end if;
  if exists (
    select 1 from jsonb_array_elements(p_boxes) b
    where jsonb_typeof(b) is distinct from 'object'
       or nullif(btrim(b->>'nombre_box'), '') is null
       or coalesce(b->>'aves_hembra_inicial', '') !~ '^[0-9]+$'
       or coalesce(b->>'aves_macho_inicial', '') !~ '^[0-9]+$'
       or (b->>'id' is not null and b->>'id' !~ '^-?[0-9]+$')
  ) then
    raise exception 'Invalid box name, ID or initial bird count' using errcode = '22023';
  end if;
  if (select count(*) from jsonb_array_elements(p_boxes)) <>
     (select count(distinct btrim(b->>'nombre_box')) from jsonb_array_elements(p_boxes) b) then
    raise exception 'Box names must be unique' using errcode = '22023';
  end if;
  select sum((b->>'aves_hembra_inicial')::bigint), sum((b->>'aves_macho_inicial')::bigint),
         array_agg((b->>'id')::bigint) filter (where b->>'id' is not null)
  into v_hembras, v_machos, v_ids
  from jsonb_array_elements(p_boxes) b;
  v_ids := coalesce(v_ids, array[]::bigint[]);
  if v_hembras + v_machos not between 1 and 2147483647 then
    raise exception 'Invalid total bird count' using errcode = '22023';
  end if;
  if cardinality(v_ids) <> (select count(distinct i) from unnest(v_ids) i) then
    raise exception 'A box ID may only appear once' using errcode = '22023';
  end if;

  select g.granja_id into v_granja_id from public.galpones g
  where g.id = (p_lote->>'galpon_id')::bigint;
  if not coalesce(private.user_can_access_farm(v_granja_id, true), false) then
    raise exception 'No write access to destination farm' using errcode = '42501';
  end if;

  if v_lote_id is not null then
    if not private.user_can_access_lote(v_lote_id, true) then
      raise exception 'No write access to lot' using errcode = '42501';
    end if;
    select l.activo into v_activo from public.lotes l where l.id = v_lote_id for update;
    if not found or v_activo is distinct from true then
      raise exception 'Only active lots can be edited' using errcode = '22023';
    end if;
    perform b.id from public.galpon_boxes b where b.lote_id = v_lote_id order by b.id for update;
    select count(*) into v_count from public.galpon_boxes b
    where b.lote_id = v_lote_id and b.id = any(v_ids);
    if v_count <> cardinality(v_ids) then
      raise exception 'Box does not belong to this lot' using errcode = '22023';
    end if;
    if exists (
      select 1 from public.galpon_boxes b
      where b.lote_id = v_lote_id and not (b.id = any(v_ids))
        and (exists(select 1 from public.registros_diarios_box r where r.box_id = b.id)
          or exists(select 1 from public.mediciones_produccion m where m.box_id = b.id))
    ) then
      raise exception 'Boxes with historical measurements must be retained' using errcode = '23503';
    end if;
    update public.lotes set
      galpon_id = (p_lote->>'galpon_id')::bigint,
      codigo_lote = btrim(p_lote->>'codigo_lote'),
      proposito = p_lote->>'proposito',
      tipo_produccion = coalesce(p_lote->>'tipo_produccion', 'engorde'),
      linea_genetica = p_lote->>'linea_genetica',
      fecha_encaste = (p_lote->>'fecha_encaste')::date,
      aves_hembra = v_hembras, aves_macho = v_machos, aves_totales = v_hembras + v_machos
    where id = v_lote_id;
    if not found then
      raise exception 'Lot could not be updated' using errcode = '42501';
    end if;
    delete from public.galpon_boxes b where b.lote_id = v_lote_id and not (b.id = any(v_ids));
  else
    if cardinality(v_ids) > 0 then
      raise exception 'New lots cannot reuse existing box IDs' using errcode = '22023';
    end if;
    insert into public.lotes (
      galpon_id, codigo_lote, proposito, tipo_produccion, linea_genetica, fecha_encaste,
      aves_hembra, aves_macho, aves_totales, activo
    ) values (
      (p_lote->>'galpon_id')::bigint, btrim(p_lote->>'codigo_lote'), p_lote->>'proposito',
      coalesce(p_lote->>'tipo_produccion','engorde'), p_lote->>'linea_genetica',
      (p_lote->>'fecha_encaste')::date, v_hembras, v_machos, v_hembras + v_machos, true
    ) returning id into v_lote_id;
  end if;

  for v_box in select value from jsonb_array_elements(p_boxes)
  loop
    if v_box->>'id' is not null then
      update public.galpon_boxes set nombre_box = btrim(v_box->>'nombre_box'),
        aves_hembra_inicial = (v_box->>'aves_hembra_inicial')::integer,
        aves_macho_inicial = (v_box->>'aves_macho_inicial')::integer
      where id = (v_box->>'id')::bigint and lote_id = v_lote_id;
      if not found then
        raise exception 'Box could not be updated' using errcode = '42501';
      end if;
    else
      insert into public.galpon_boxes(lote_id,nombre_box,aves_hembra_inicial,aves_macho_inicial)
      values(v_lote_id,btrim(v_box->>'nombre_box'),(v_box->>'aves_hembra_inicial')::integer,(v_box->>'aves_macho_inicial')::integer);
    end if;
  end loop;
  return v_lote_id;
end;
$$;
revoke all on function public.save_lote_with_boxes(jsonb,jsonb,bigint) from public, anon;
grant execute on function public.save_lote_with_boxes(jsonb,jsonb,bigint) to authenticated;
