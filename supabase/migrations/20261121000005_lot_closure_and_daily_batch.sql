-- Lifecycle operations share the same lot lock so closing and capture serialize.
create or replace function public.close_lote(
  p_lote_id bigint, p_fecha_cierre date, p_motivo text, p_peso_cierre_g numeric
) returns bigint
language plpgsql security invoker set search_path = '' as $$
declare
  v_lote public.lotes;
begin
  if auth.uid() is null or not private.user_can_access_lote(p_lote_id, true) then
    raise exception 'No write access to lot' using errcode='42501';
  end if;
  select * into v_lote from public.lotes where id=p_lote_id for update;
  if not found then raise exception 'Lot not found' using errcode='22023'; end if;
  if p_fecha_cierre is null or p_fecha_cierre<v_lote.fecha_encaste or p_fecha_cierre>current_date
     or nullif(btrim(p_motivo),'') is null or p_peso_cierre_g is null
     or p_peso_cierre_g<=0 or p_peso_cierre_g::text in ('NaN','Infinity','-Infinity') then
    raise exception 'Invalid closure date, reason or final weight' using errcode='22023';
  end if;
  if v_lote.activo is distinct from true then
    if (v_lote.fecha_cierre,v_lote.motivo_cierre,v_lote.peso_cierre_g)
       is not distinct from (p_fecha_cierre,btrim(p_motivo),p_peso_cierre_g) then
      return p_lote_id;
    end if;
    raise exception 'Lot is already closed with different closure data' using errcode='22023';
  end if;
  if exists(select 1 from public.registros_diarios where lote_id=p_lote_id and fecha>p_fecha_cierre) then
    raise exception 'Closure cannot precede a production record' using errcode='22023';
  end if;
  update public.lotes set activo=false, fecha_cierre=p_fecha_cierre,
    motivo_cierre=btrim(p_motivo), peso_cierre_g=p_peso_cierre_g where id=p_lote_id;
  if not found then raise exception 'Lot could not be closed' using errcode='42501'; end if;
  return p_lote_id;
end $$;
revoke all on function public.close_lote(bigint,date,text,numeric) from public,anon;
grant execute on function public.close_lote(bigint,date,text,numeric) to authenticated;

create or replace function public.save_daily_record(p_lote_id bigint,p_fecha date,p_boxes jsonb)
returns bigint language plpgsql security invoker set search_path = '' as $$
declare
  v_lote public.lotes;
  v_daily_id bigint;
  v_ids bigint[];
  v_n integer;
begin
  if auth.uid() is null or not private.user_can_access_lote(p_lote_id,true) then
    raise exception 'No write access to lot' using errcode='42501';
  end if;
  select * into v_lote from public.lotes where id=p_lote_id for update;
  if not found or v_lote.activo is distinct from true then
    raise exception 'Only active lots accept daily capture' using errcode='22023';
  end if;
  if p_fecha is null or p_fecha<v_lote.fecha_encaste or p_fecha>current_date then
    raise exception 'Invalid daily record date' using errcode='22023';
  end if;
  if jsonb_typeof(p_boxes) is distinct from 'array' or jsonb_array_length(p_boxes)<1 then
    raise exception 'A nonempty box array is required' using errcode='22023';
  end if;
  if exists(select 1 from jsonb_array_elements(p_boxes) b
    where jsonb_typeof(b) is distinct from 'object'
      or coalesce(b->>'box_id','') !~ '^-?[0-9]+$'
      or coalesce(b->>'mortalidad_hembra','') !~ '^[0-9]+$'
      or coalesce(b->>'mortalidad_macho','') !~ '^[0-9]+$'
      or coalesce(b->>'descarte_hembra','') !~ '^[0-9]+$'
      or coalesce(b->>'descarte_macho','') !~ '^[0-9]+$'
      or jsonb_typeof(b->'consumo_alimento_kg') is distinct from 'number'
      or jsonb_typeof(b->'consumo_agua_litros') is distinct from 'number'
      or jsonb_typeof(coalesce(b->'metricas','[]'::jsonb)) is distinct from 'array'
  ) then raise exception 'Invalid box data' using errcode='22023'; end if;

  select array_agg((b->>'box_id')::bigint) into v_ids from jsonb_array_elements(p_boxes)b;
  select count(*) into v_n from public.galpon_boxes where lote_id=p_lote_id;
  if v_n<>cardinality(v_ids) or cardinality(v_ids)<>(select count(distinct i) from unnest(v_ids)i)
     or exists(select 1 from unnest(v_ids)i where not exists(
       select 1 from public.galpon_boxes b where b.id=i and b.lote_id=p_lote_id)) then
    raise exception 'Capture must contain every lot box exactly once' using errcode='22023';
  end if;
  if exists(select 1 from jsonb_to_recordset(p_boxes) as x(
      consumo_alimento_kg numeric,consumo_agua_litros numeric,
      peso_promedio_hembra_g numeric,peso_promedio_macho_g numeric)
    where x.consumo_alimento_kg<0 or x.consumo_agua_litros<0
      or x.peso_promedio_hembra_g<0 or x.peso_promedio_macho_g<0
      or x.peso_promedio_hembra_g::text in ('NaN','Infinity','-Infinity')
      or x.peso_promedio_macho_g::text in ('NaN','Infinity','-Infinity')
  ) then raise exception 'Production values must be finite and nonnegative' using errcode='22023'; end if;
  if exists(
    select 1 from jsonb_array_elements(p_boxes)b
    cross join lateral jsonb_array_elements(coalesce(b->'metricas','[]'::jsonb))m
    where jsonb_typeof(m) is distinct from 'object'
      or jsonb_typeof(m->'valor') is distinct from 'number'
      or (m->>'valor')::numeric<0
      or not exists(select 1 from public.metricas_produccion c
        where c.codigo=m->>'codigo_metrica' and c.activa and v_lote.tipo_produccion=any(c.tipos_produccion))
  ) then raise exception 'Invalid metric or metric not allowed for this production type' using errcode='22023'; end if;
  if exists(select 1 from jsonb_array_elements(p_boxes)b
    cross join lateral jsonb_array_elements(coalesce(b->'metricas','[]'::jsonb))m
    group by b->>'box_id',m->>'codigo_metrica' having count(*)>1
  ) then raise exception 'Duplicate box metric' using errcode='22023'; end if;

  -- Reject corrections whose lifetime losses would exceed the initial population.
  if exists(
    select 1 from jsonb_to_recordset(p_boxes) as x(box_id bigint,mortalidad_hembra integer,
      mortalidad_macho integer,descarte_hembra integer,descarte_macho integer)
    join public.galpon_boxes b on b.id=x.box_id
    left join lateral (
      select coalesce(sum(coalesce(r.mortalidad_hembra,0)+coalesce(r.descarte_hembra,0)),0) h,
             coalesce(sum(coalesce(r.mortalidad_macho,0)+coalesce(r.descarte_macho,0)),0) m
      from public.registros_diarios_box r join public.registros_diarios d on d.id=r.registro_diario_id
      where r.box_id=b.id and d.fecha<>p_fecha
    ) prev on true
    where prev.h+x.mortalidad_hembra+x.descarte_hembra>coalesce(b.aves_hembra_inicial,0)
       or prev.m+x.mortalidad_macho+x.descarte_macho>coalesce(b.aves_macho_inicial,0)
  ) then raise exception 'Accumulated losses exceed the initial box population' using errcode='22023'; end if;

  insert into public.registros_diarios(lote_id,fecha,dia_vida)
  values(p_lote_id,p_fecha,p_fecha-v_lote.fecha_encaste+1)
  on conflict(lote_id,fecha) do update set dia_vida=excluded.dia_vida
  returning id into v_daily_id;

  insert into public.registros_diarios_box(registro_diario_id,box_id,mortalidad_hembra,
    mortalidad_macho,descarte_hembra,descarte_macho,consumo_alimento_kg,consumo_agua_litros,
    peso_promedio_hembra_g,peso_promedio_macho_g)
  select v_daily_id,x.box_id,x.mortalidad_hembra,x.mortalidad_macho,x.descarte_hembra,
    x.descarte_macho,x.consumo_alimento_kg,x.consumo_agua_litros,
    x.peso_promedio_hembra_g,x.peso_promedio_macho_g
  from jsonb_to_recordset(p_boxes) as x(box_id bigint,mortalidad_hembra integer,
    mortalidad_macho integer,descarte_hembra integer,descarte_macho integer,
    consumo_alimento_kg numeric,consumo_agua_litros numeric,
    peso_promedio_hembra_g numeric,peso_promedio_macho_g numeric)
  order by x.box_id
  on conflict(registro_diario_id,box_id) do update set
    mortalidad_hembra=excluded.mortalidad_hembra,mortalidad_macho=excluded.mortalidad_macho,
    descarte_hembra=excluded.descarte_hembra,descarte_macho=excluded.descarte_macho,
    consumo_alimento_kg=excluded.consumo_alimento_kg,consumo_agua_litros=excluded.consumo_agua_litros,
    peso_promedio_hembra_g=excluded.peso_promedio_hembra_g,peso_promedio_macho_g=excluded.peso_promedio_macho_g;
  delete from public.mediciones_produccion where registro_diario_id=v_daily_id and box_id=any(v_ids);
  insert into public.mediciones_produccion(registro_diario_id,box_id,codigo_metrica,valor)
  select v_daily_id,(b->>'box_id')::bigint,m->>'codigo_metrica',(m->>'valor')::numeric
  from jsonb_array_elements(p_boxes)b
  cross join lateral jsonb_array_elements(coalesce(b->'metricas','[]'::jsonb))m;
  return v_daily_id;
end $$;
revoke all on function public.save_daily_record(bigint,date,jsonb) from public,anon;
grant execute on function public.save_daily_record(bigint,date,jsonb) to authenticated;

-- Protect direct Data API writes as well as the application RPC.
create or replace function private.require_active_lot_for_daily_write()
returns trigger language plpgsql security invoker set search_path='' as $$
declare v_old_lot bigint; v_new_lot bigint; v_lot record;
begin
  if tg_table_name='registros_diarios' then
    v_new_lot:=new.lote_id;
    if tg_op='UPDATE' then v_old_lot:=old.lote_id; end if;
  else
    select lote_id into v_new_lot from public.registros_diarios where id=new.registro_diario_id;
    if tg_op='UPDATE' then
      select lote_id into v_old_lot from public.registros_diarios where id=old.registro_diario_id;
    end if;
  end if;
  if v_new_lot is null or (tg_op='UPDATE' and v_old_lot is null) then
    raise exception 'Daily parent not found' using errcode='23514';
  end if;
  for v_lot in select id,activo from public.lotes
    where id=any(array[v_old_lot,v_new_lot]) order by id for update
  loop
    if v_lot.activo is distinct from true then
      raise exception 'Daily capture requires active source and destination lots' using errcode='23514';
    end if;
  end loop;
  return new;
end $$;
revoke all on function private.require_active_lot_for_daily_write() from public,anon,authenticated;
drop trigger if exists registros_diarios_require_active_lot on public.registros_diarios;
create trigger registros_diarios_require_active_lot before insert or update on public.registros_diarios
for each row when (current_user='authenticated') execute function private.require_active_lot_for_daily_write();
drop trigger if exists registros_diarios_box_require_active_lot on public.registros_diarios_box;
create trigger registros_diarios_box_require_active_lot before insert or update on public.registros_diarios_box
for each row when (current_user='authenticated') execute function private.require_active_lot_for_daily_write();
drop trigger if exists mediciones_produccion_require_active_lot on public.mediciones_produccion;
create trigger mediciones_produccion_require_active_lot before insert or update on public.mediciones_produccion
for each row when (current_user='authenticated') execute function private.require_active_lot_for_daily_write();
